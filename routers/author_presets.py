# routers/author_presets.py
import re
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from db.manager import db
from utils.deps import get_current_user
from utils.llm_provider import LLMFactory
from core.prompts import AUTHOR_ANALYSIS_PROMPT, AUTHOR_EXAMPLE_GEN_PROMPT
from utils.logger import Logger
from core.rag import StyleRAGManager  # 🔥 引入新管理器

router = APIRouter(prefix="/author-presets", tags=["Author Presets"])


# --- Models ---
class AuthorCreateRequest(BaseModel):
    author_name: str


class AuthorUpdateRequest(BaseModel):
    style_profile: str


class SampleCreateRequest(BaseModel):
    author_preset_id: int
    title: str = "AI 生成例章"
    content: str


class GenerateSampleRequest(BaseModel):
    author_preset_id: int
    topic: Optional[str] = "通用场景"


# --- Background Tasks ---

def bg_analyze_author(preset_id: int, author_name: str, user_id: int):
    logger = Logger(project_id=None)
    try:
        llm = LLMFactory.create(project_id=None, user_id=user_id, role="author")
        profile = llm.generate_text(
            system_prompt="你是一位资深文学评论家。",
            user_prompt=AUTHOR_ANALYSIS_PROMPT.format(author_name=author_name)
        )
        db.execute(
            "UPDATE author_presets SET style_profile = ?, status = 'completed' WHERE id = ?",
            (profile, preset_id)
        )
        print(f"✅ [后台任务] 作家 {author_name} 分析完成。")
    except Exception as e:
        print(f"❌ [后台任务] 分析失败: {e}")
        db.execute(
            "UPDATE author_presets SET style_profile = ?, status = 'failed' WHERE id = ?",
            (f"分析失败: {str(e)}", preset_id)
        )


def bg_generate_example(preset_id: int, user_id: int, topic: str):
    """后台生成例章任务 + 自动入库向量"""
    try:
        row = db.fetch_one("SELECT author_name, style_profile FROM author_presets WHERE id = ?", (preset_id,))
        if not row: return
        name, profile = row

        llm = LLMFactory.create(project_id=None, user_id=user_id, role="author")

        raw_text = llm.generate_text(
            system_prompt="你是一个文风模仿大师。",
            user_prompt=AUTHOR_EXAMPLE_GEN_PROMPT.format(author_name=name, style_profile=profile)
        )

        title = f"AI仿写-{name}"
        content = raw_text

        try:
            title_match = re.search(r'^[\*\#]*\s*(标题|Title)[:：]\s*(.*)', raw_text, re.MULTILINE | re.IGNORECASE)
            content_match = re.search(r'^[\*\#]*\s*(内容|Content)[:：]', raw_text, re.MULTILINE | re.IGNORECASE)

            if title_match:
                title = title_match.group(2).strip()

            if content_match:
                start_idx = content_match.end()
                content = raw_text[start_idx:].strip()
            elif title_match:
                content = raw_text[title_match.end():].strip()

            content = content.replace("```", "").strip()
        except Exception as e:
            print(f"⚠️ 解析 AI 例章格式失败: {e}")

        # 1. 存入 SQL
        sample_id = db.execute(
            "INSERT INTO style_references (user_id, name, content, author_preset_id) VALUES (?, ?, ?, ?)",
            (user_id, title, content, preset_id)
        )

        # 2. 🔥 存入 Chroma 向量库
        rag = StyleRAGManager(user_id)
        rag.add_sample(sample_id, preset_id, content, title)

        print(f"✅ [后台任务] 例章生成并索引完成: {title}")

    except Exception as e:
        print(f"❌ [后台任务] 例章生成失败: {e}")


# --- Endpoints ---

@router.post("/add")
def add_author(req: AuthorCreateRequest, bg_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    user_id = current_user['id']
    try:
        preset_id = db.execute(
            "INSERT INTO author_presets (user_id, author_name, style_profile, status) VALUES (?, ?, ?, 'analyzing')",
            (user_id, req.author_name, "正在深入研读该作家的作品，分析其文风基因...")
        )
        bg_tasks.add_task(bg_analyze_author, preset_id, req.author_name, user_id)
        return {"status": "started", "id": preset_id, "message": "分析任务已提交后台"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{id}/retry")
def retry_analysis(id: int, bg_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    row = db.fetch_one("SELECT author_name FROM author_presets WHERE id = ? AND user_id = ?", (id, current_user['id']))
    if not row: raise HTTPException(status_code=404)
    db.execute("UPDATE author_presets SET status = 'analyzing' WHERE id = ?", (id,))
    bg_tasks.add_task(bg_analyze_author, id, row[0], current_user['id'])
    return {"status": "restarted"}


@router.put("/{id}")
def update_profile(id: int, req: AuthorUpdateRequest, current_user: dict = Depends(get_current_user)):
    if not db.fetch_one("SELECT id FROM author_presets WHERE id = ? AND user_id = ?", (id, current_user['id'])):
        raise HTTPException(status_code=404)
    db.execute("UPDATE author_presets SET style_profile = ? WHERE id = ?", (req.style_profile, id))
    return {"status": "success"}


@router.get("/list")
def list_authors(current_user: dict = Depends(get_current_user)):
    rows = db.fetch_all(
        "SELECT id, author_name, style_profile, status, created_at FROM author_presets WHERE user_id = ? ORDER BY id DESC",
        (current_user['id'],)
    )
    return [
        {"id": r[0], "author_name": r[1], "style_profile": r[2], "status": r[3], "preview": r[2][:60] + "..." if r[2] else "", "created_at": r[4]}
        for r in rows
    ]


@router.delete("/{id}")
def delete_author(id: int, current_user: dict = Depends(get_current_user)):
    if not db.fetch_one("SELECT id FROM author_presets WHERE id = ? AND user_id = ?", (id, current_user['id'])):
        raise HTTPException(status_code=404)

    # 级联删除 style_references (SQL)，但 Chroma 需要手动删
    # 先查出所有相关的 sample_ids
    sample_rows = db.fetch_all("SELECT id FROM style_references WHERE author_preset_id = ?", (id,))

    rag = StyleRAGManager(current_user['id'])
    for r in sample_rows:
        rag.delete_sample(r[0])

    db.execute("DELETE FROM style_references WHERE author_preset_id = ?", (id,))
    db.execute("DELETE FROM author_presets WHERE id = ?", (id,))
    return {"status": "success"}


# --- 例章 ---

@router.get("/{id}/samples")
def list_samples(id: int, current_user: dict = Depends(get_current_user)):
    rows = db.fetch_all(
        "SELECT id, name, content FROM style_references WHERE author_preset_id = ? AND user_id = ? ORDER BY id DESC",
        (id, current_user['id'])
    )
    return [{"id": r[0], "name": r[1], "content": r[2]} for r in rows]


@router.post("/samples/generate")
def generate_ai_sample(req: GenerateSampleRequest, bg_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    bg_tasks.add_task(bg_generate_example, req.author_preset_id, current_user['id'], req.topic)
    return {"status": "started", "message": "AI 正在模仿创作..."}


@router.post("/samples/add")
def add_manual_sample(req: SampleCreateRequest, current_user: dict = Depends(get_current_user)):
    try:
        # 1. SQL
        sample_id = db.execute(
            "INSERT INTO style_references (user_id, name, content, author_preset_id) VALUES (?, ?, ?, ?)",
            (current_user['id'], req.title, req.content, req.author_preset_id)
        )
        # 2. 🔥 Chroma
        rag = StyleRAGManager(current_user['id'])
        rag.add_sample(sample_id, req.author_preset_id, req.content, req.title)

        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/samples/{sample_id}")
def delete_sample(sample_id: int, current_user: dict = Depends(get_current_user)):
    # 1. Chroma
    rag = StyleRAGManager(current_user['id'])
    rag.delete_sample(sample_id)

    # 2. SQL
    db.execute("DELETE FROM style_references WHERE id = ? AND user_id = ?", (sample_id, current_user['id']))
    return {"status": "success"}