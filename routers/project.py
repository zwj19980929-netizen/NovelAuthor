# routers/project.py
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict
from urllib.parse import quote

from core.engine import TrinityEngine
from db.manager import db
from utils.deps import get_current_user
from utils.logger import Logger
from utils.llm_provider import LLMFactory
from core.prompts import EXPAND_PROMPT, POLISH_PROMPT
from utils.exporter import generate_word_doc, generate_txt_doc
from utils.sse_manager import sse_manager

router = APIRouter(prefix="/project", tags=["Project"])
engine = TrinityEngine()


# --- Request Models ---

class InitProjectRequest(BaseModel):
    name: str
    keywords: str
    style_desc: str
    auto_start: bool = True
    target_word_count: int = 2000
    total_chapters: int = 20
    architect_model_id: Optional[int] = None
    writer_model_id: Optional[int] = None
    narrative_view: str = 'third'
    style_ref_id: Optional[int] = None


class GenerateBatchRequest(BaseModel):
    project_id: int
    human_instruction: str = ""


class RollbackRequest(BaseModel):
    project_id: int
    target_chapter: int


class AddCharacterRequest(BaseModel):
    project_id: int
    name: str
    archetype: str
    desc: str
    target: str = "未知"
    fear: str = "未知"
    role: str = "配角"


class EditCharacterRequest(BaseModel):
    project_id: int
    character_name: str
    new_name: Optional[str] = None
    archetype: Optional[str] = None
    desc: Optional[str] = None
    target: Optional[str] = None
    fear: Optional[str] = None
    role: Optional[str] = None


class AssistRequest(BaseModel):
    project_id: int
    text: str
    action: str
    context: str = ""


# --- Helper Functions ---

def background_init_and_start(project_id: int, keywords: str, style_desc: str):
    logger = Logger(project_id)
    try:
        logger.info("⚡ 后台任务已启动，正在初始化世界观...")
        engine.async_build_world(project_id, keywords, style_desc)
        logger.info("⚡ 初始化完成，自动启动正文生成...")
        engine.run_batch(project_id, human_instruction="")
    except Exception as e:
        import traceback
        logger.error(f"后台任务异常中断: {str(e)}")
        print(traceback.format_exc())


def run_generation_task(project_id: int, instruction: str):
    logger = Logger(project_id)
    try:
        logger.info("⚡ 手动生成任务已启动...")
        engine.run_batch(project_id, instruction)
    except Exception as e:
        import traceback
        logger.error(f"生成任务失败: {str(e)}")
        print(traceback.format_exc())


def verify_project_owner(project_id: int, user_id: int):
    row = db.fetch_one("SELECT id FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id))
    if not row:
        raise HTTPException(status_code=403, detail="Permission denied or Project not found")


# --- Endpoints ---

@router.post("/create")
def create_project(
        req: InitProjectRequest,
        background_tasks: BackgroundTasks,
        current_user: dict = Depends(get_current_user)
):
    try:
        from datetime import datetime

        default_cred_id = None
        user_default = db.fetch_one("SELECT id FROM llm_credentials WHERE user_id = ? AND is_active = 1 LIMIT 1", (current_user['id'],))
        if user_default:
            default_cred_id = user_default[0]

        arch_id = req.architect_model_id if req.architect_model_id else default_cred_id
        writ_id = req.writer_model_id if req.writer_model_id else default_cred_id

        view_text = "第一人称 (我)" if req.narrative_view == 'first' else "第三人称 (他/她/它)"
        final_style_desc = f"{req.style_desc}\n\n【强制要求】：全文必须严格使用{view_text}叙事，严禁切换视角。"

        project_id = db.execute(
            """INSERT INTO projects 
               (user_id, name, keywords, style_desc, world_config, llm_credential_id, writer_credential_id, target_word_count, total_chapters, style_ref_id, created_at) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                current_user['id'],
                req.name,
                req.keywords,
                final_style_desc,
                "{}",
                arch_id,
                writ_id,
                req.target_word_count,
                req.total_chapters,
                req.style_ref_id,
                datetime.now()
            )
        )

        if req.auto_start:
            background_tasks.add_task(background_init_and_start, project_id, req.keywords, final_style_desc)
        else:
            background_tasks.add_task(engine.async_build_world, project_id, req.keywords, final_style_desc)

        return {"project_id": project_id, "message": "Project initializing..."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
def list_my_projects(current_user: dict = Depends(get_current_user)):
    rows = db.fetch_all(
        "SELECT id, name, created_at, keywords FROM projects WHERE user_id = ? ORDER BY id DESC",
        (current_user['id'],)
    )
    return [{"id": r[0], "name": r[1], "created_at": r[2], "keywords": r[3]} for r in rows]


@router.delete("/{project_id}")
def delete_project(project_id: int, current_user: dict = Depends(get_current_user)):
    verify_project_owner(project_id, current_user['id'])

    try:
        db.execute("DELETE FROM system_logs WHERE project_id = ?", (project_id,))
        db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return {"status": "success", "message": "Project deleted completely"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.get("/{project_id}/details")
def get_project_details(project_id: int, current_user: dict = Depends(get_current_user)):
    verify_project_owner(project_id, current_user['id'])

    # 1. 基础信息
    row = db.fetch_one("SELECT name, keywords, style_desc, world_config, target_word_count, total_chapters FROM projects WHERE id = ?", (project_id,))
    if not row: raise HTTPException(status_code=404)

    world_config = json.loads(row[3]) if row[3] else {}
    target_wc = row[4]
    total_chapters = row[5]

    # 2. 宏观大纲
    arc_row = db.fetch_one(
        "SELECT hook, journey, climax, resolution FROM global_arcs WHERE project_id = ? AND is_active = 1 ORDER BY id DESC LIMIT 1",
        (project_id,)
    )
    global_arc_data = {}
    if arc_row:
        global_arc_data = {"hook": arc_row[0], "journey": arc_row[1], "climax": arc_row[2], "resolution": arc_row[3]}

    # 3. 🔥 新增：分章细纲列表
    # 从 chapter_outlines 表获取所有已生成的细纲
    outlines_rows = db.fetch_all(
        "SELECT chapter_num, title, plot_point, visual_key FROM chapter_outlines WHERE project_id = ? ORDER BY chapter_num ASC",
        (project_id,)
    )
    chapter_outlines = []
    for r in outlines_rows:
        chapter_outlines.append({
            "chapter_num": r[0],
            "title": r[1],
            "plot_point": r[2],
            "visual_key": r[3]
        })

    # 4. 角色列表 (保持原逻辑)
    latest_chap_row = db.fetch_one("SELECT MAX(chapter_num) FROM character_states WHERE project_id = ?", (project_id,))
    latest_chap = latest_chap_row[0] if latest_chap_row and latest_chap_row[0] is not None else 0

    sql = """
    SELECT c.name, c.archetype, c.core_vector, c.role,
           s.location, s.current_status, s.inventory, s.relationships
    FROM characters c
    LEFT JOIN character_states s ON c.id = s.character_id AND s.chapter_num = ?
    WHERE c.project_id = ?
    ORDER BY CASE c.role 
        WHEN '主角' THEN 1 
        WHEN '反派' THEN 2 
        WHEN '配角' THEN 3 
        ELSE 4 END ASC, c.id ASC
    """
    rows = db.fetch_all(sql, (latest_chap, project_id))

    char_list = []
    for r in rows:
        name, archetype, vec_json, role, loc, status, inv_json, rel_json = r
        char_list.append({
            "name": name,
            "archetype": archetype,
            "role": role if role else "配角",
            "vector": json.loads(vec_json) if vec_json else {},
            "current_status": status if status else "暂无状态",
            "location": loc if loc else "未知",
            "inventory": json.loads(inv_json) if inv_json else [],
            "relationships": json.loads(rel_json) if rel_json else {}
        })

    return {
        "name": row[0],
        "keywords": row[1],
        "style_desc": row[2],
        "target_word_count": target_wc,
        "total_chapters": total_chapters,
        "global_arc": global_arc_data,
        "chapter_outlines": chapter_outlines, # 🔥 返回细纲列表
        "world_context": {
            "physics": world_config.get("physics", {}),
            "characters": char_list
        }
    }


@router.post("/generate")
def generate_batch(req: GenerateBatchRequest, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    verify_project_owner(req.project_id, current_user['id'])
    background_tasks.add_task(run_generation_task, req.project_id, req.human_instruction)
    return {"status": "started"}


@router.post("/character/add")
def add_character(req: AddCharacterRequest, current_user: dict = Depends(get_current_user)):
    verify_project_owner(req.project_id, current_user['id'])
    try:
        vector_data = {
            "target": req.target if req.target else "未知",
            "fear": req.fear if req.fear else "未知",
            "skill": "用户设定"
        }
        char_id = db.execute(
            "INSERT INTO characters (project_id, name, archetype, core_vector, role) VALUES (?, ?, ?, ?, ?)",
            (req.project_id, req.name, req.archetype, json.dumps(vector_data, ensure_ascii=False), req.role)
        )
        latest_chap_row = db.fetch_one("SELECT MAX(chapter_num) FROM chapters WHERE project_id = ?", (req.project_id,))
        latest_chap = latest_chap_row[0] if latest_chap_row and latest_chap_row[0] else 0
        db.execute(
            """INSERT INTO character_states 
               (character_id, project_id, chapter_num, location, current_status, inventory, relationships)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (char_id, req.project_id, latest_chap, "未知", req.desc, "[]", "{}")
        )
        Logger(req.project_id).info(f"👋 用户手动添加角色: {req.name} ({req.role})")
        return {"status": "success", "message": "Character added"}
    except Exception as e:
        if "UNIQUE constraint failed" in str(e):
            raise HTTPException(status_code=400, detail="角色名已存在")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/character/update")
def update_character(req: EditCharacterRequest, current_user: dict = Depends(get_current_user)):
    verify_project_owner(req.project_id, current_user['id'])

    row = db.fetch_one("SELECT id, core_vector FROM characters WHERE project_id = ? AND name = ?", (req.project_id, req.character_name))
    if not row:
        raise HTTPException(status_code=404, detail="角色未找到")

    char_id = row[0]
    current_vector = json.loads(row[1]) if row[1] else {}

    fields = []
    values = []

    if req.new_name:
        fields.append("name = ?")
        values.append(req.new_name)
    if req.archetype:
        fields.append("archetype = ?")
        values.append(req.archetype)
    if req.role:
        fields.append("role = ?")
        values.append(req.role)

    is_vector_changed = False
    if req.target:
        current_vector["target"] = req.target
        is_vector_changed = True
    if req.fear:
        current_vector["fear"] = req.fear
        is_vector_changed = True

    if is_vector_changed:
        fields.append("core_vector = ?")
        values.append(json.dumps(current_vector, ensure_ascii=False))

    if fields:
        values.append(char_id)
        sql = f"UPDATE characters SET {', '.join(fields)} WHERE id = ?"
        try:
            db.execute(sql, tuple(values))
        except Exception as e:
            if "UNIQUE" in str(e):
                raise HTTPException(status_code=400, detail="新名字已存在")
            raise e

    if req.desc:
        latest_chap_row = db.fetch_one("SELECT MAX(chapter_num) FROM character_states WHERE project_id = ?", (req.project_id,))
        latest_chap = latest_chap_row[0] if latest_chap_row and latest_chap_row[0] is not None else 0

        state_row = db.fetch_one("SELECT id FROM character_states WHERE character_id = ? AND chapter_num = ?", (char_id, latest_chap))
        if state_row:
            db.execute("UPDATE character_states SET current_status = ? WHERE id = ?", (req.desc, state_row[0]))
        else:
            db.execute(
                """INSERT INTO character_states (character_id, project_id, chapter_num, location, current_status, inventory, relationships)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (char_id, req.project_id, latest_chap, "未知", req.desc, "[]", "{}")
            )

    Logger(req.project_id).info(f"✏️ 角色信息已更新: {req.new_name if req.new_name else req.character_name}")
    return {"status": "success"}


@router.post("/assist")
def ai_assist(req: AssistRequest, current_user: dict = Depends(get_current_user)):
    verify_project_owner(req.project_id, current_user['id'])

    row = db.fetch_one("SELECT style_desc, world_config FROM projects WHERE id = ?", (req.project_id,))
    if not row: raise HTTPException(status_code=404)
    style_desc, world_config = row[0], json.loads(row[1]) if row[1] else {}

    world_info = json.dumps(world_config.get("physics", {}), ensure_ascii=False)
    char_rows = db.fetch_all("SELECT name, archetype FROM characters WHERE project_id = ?", (req.project_id,))
    char_info = ", ".join([f"{r[0]}({r[1]})" for r in char_rows])

    llm = LLMFactory.create(project_id=req.project_id, role="writer")

    prompt_template = EXPAND_PROMPT if req.action == "expand" else POLISH_PROMPT
    full_prompt = prompt_template.format(text=req.text, context=req.context, style_desc=style_desc, world_context=world_info, char_info=char_info)

    try:
        result = llm.generate_text(system_prompt="你是一个辅助写作AI，必须严格遵守给定的世界观设定。", user_prompt=full_prompt)
        return {"result": result}
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"AI Assist Error: {str(e)}")


@router.get("/{project_id}/state")
def get_project_state(project_id: int, current_user: dict = Depends(get_current_user)):
    verify_project_owner(project_id, current_user['id'])

    row_chap = db.fetch_one("SELECT MAX(chapter_num) FROM chapters WHERE project_id = ?", (project_id,))
    current_chapter = row_chap[0] if row_chap and row_chap[0] else 0

    row_content = db.fetch_all("SELECT content FROM chapters WHERE project_id = ?", (project_id,))
    total_chars = sum([len(r[0]) for r in row_content]) if row_content else 0
    estimated_tokens = int(total_chars / 1.5)

    proj_row = db.fetch_one("SELECT total_chapters FROM projects WHERE id = ?", (project_id,))
    total_chapters = proj_row[0] if proj_row and proj_row[0] else 20

    return {
        "current_chapter": current_chapter,
        "total_tokens": estimated_tokens,
        "status": "Ready",
        "total_chapters": total_chapters
    }


@router.get("/{project_id}/logs")
def get_logs(project_id: int, current_user: dict = Depends(get_current_user)):
    verify_project_owner(project_id, current_user['id'])
    rows = db.fetch_all("SELECT timestamp, level, message FROM system_logs WHERE project_id = ? ORDER BY id DESC LIMIT 50", (project_id,))
    return [{"time": r[0], "level": r[1], "msg": r[2]} for r in rows]


@router.get("/{project_id}/chapters")
def get_chapters_list(project_id: int, current_user: dict = Depends(get_current_user)):
    verify_project_owner(project_id, current_user['id'])
    rows = db.fetch_all("SELECT chapter_num, title, content FROM chapters WHERE project_id = ? ORDER BY chapter_num ASC", (project_id,))
    return [{"chapter_num": r[0], "title": r[1], "content": r[2], "preview": r[2][:50] + "..." if r[2] else ""} for r in rows]


@router.get("/{project_id}/story")
def get_story(project_id: int, current_user: dict = Depends(get_current_user)):
    verify_project_owner(project_id, current_user['id'])
    rows = db.fetch_all("SELECT title, content FROM chapters WHERE project_id = ? ORDER BY chapter_num ASC", (project_id,))
    full_text = "\n\n".join([f"# {r[0]}\n\n{r[1]}" for r in rows])
    return {"content": full_text}


@router.post("/rollback")
def rollback_story(req: RollbackRequest, current_user: dict = Depends(get_current_user)):
    verify_project_owner(req.project_id, current_user['id'])
    try:
        engine.rollback_story(req.project_id, req.target_chapter)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/export")
def export_project(
        project_id: int,
        format: str = "docx",
        current_user: dict = Depends(get_current_user)
):
    verify_project_owner(project_id, current_user['id'])

    row = db.fetch_one("SELECT name FROM projects WHERE id = ?", (project_id,))
    project_name = row[0] if row else "未命名项目"

    rows = db.fetch_all(
        "SELECT chapter_num, title, content FROM chapters WHERE project_id = ? ORDER BY chapter_num ASC",
        (project_id,)
    )
    chapters = [{"chapter_num": r[0], "title": r[1], "content": r[2]} for r in rows]

    if not chapters:
        raise HTTPException(status_code=404, detail="暂无章节可导出")

    try:
        if format == "txt":
            file_stream = generate_txt_doc(project_name, chapters)
            media_type = "text/plain"
            filename = f"{project_name}.txt"
        else:
            file_stream = generate_word_doc(project_name, chapters)
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            filename = f"{project_name}.docx"

        encoded_filename = quote(filename)

        return StreamingResponse(
            file_stream,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/{project_id}/connect")
async def connect_sse(project_id: int):
    return StreamingResponse(
        sse_manager.connect(project_id),
        media_type="text/event-stream"
    )