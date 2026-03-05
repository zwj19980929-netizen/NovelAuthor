# routers/style_ref.py
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from db.manager import db
from utils.deps import get_current_user

router = APIRouter(prefix="/style-ref", tags=["Style Reference"])


class StyleRefCreate(BaseModel):
    name: str
    content: str


@router.post("/add")
def add_style_ref(req: StyleRefCreate, current_user: dict = Depends(get_current_user)):
    try:
        # 校验字数，太短没效果
        if len(req.content) < 50:
            raise HTTPException(status_code=400, detail="样章内容太短，建议至少 50 字。")

        style_id = db.execute(
            "INSERT INTO style_references (user_id, name, content) VALUES (?, ?, ?)",
            (current_user['id'], req.name, req.content)
        )
        return {"status": "success", "id": style_id, "name": req.name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
def list_style_refs(current_user: dict = Depends(get_current_user)):
    # 列表页不需要返回全文，只返回预览
    rows = db.fetch_all(
        "SELECT id, name, content, created_at FROM style_references WHERE user_id = ? ORDER BY id DESC",
        (current_user['id'],)
    )
    return [
        {"id": r[0], "name": r[1], "preview": r[2][:100] + "...", "full_content": r[2], "created_at": r[3]}
        for r in rows
    ]


@router.delete("/{style_id}")
def delete_style_ref(style_id: int, current_user: dict = Depends(get_current_user)):
    if not db.fetch_one("SELECT id FROM style_references WHERE id = ? AND user_id = ?", (style_id, current_user['id'])):
        raise HTTPException(status_code=404, detail="样章不存在")

    # 解除关联 (置空)
    db.execute("UPDATE projects SET style_ref_id = NULL WHERE style_ref_id = ?", (style_id,))
    # 删除记录
    db.execute("DELETE FROM style_references WHERE id = ?", (style_id,))

    return {"status": "success"}