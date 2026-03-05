import os
import uuid
import shutil
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from utils.deps import get_current_user
from db.manager import db

router = APIRouter(prefix="/images", tags=["Image Library"])

# 配置上传路径 (本地文件系统模拟 OSS)
UPLOAD_ROOT = "uploads"
os.makedirs(UPLOAD_ROOT, exist_ok=True)


@router.post("/upload")
async def upload_image(
        file: UploadFile = File(...),
        category: str = Form("general"),  # 允许前端传分类
        current_user: dict = Depends(get_current_user)
):
    user_id = current_user['id']

    # 1. 校验文件
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="仅支持上传图片格式")

    # 2. 准备路径
    # 按分类分文件夹存储，更清晰
    category_dir = os.path.join(UPLOAD_ROOT, category)
    os.makedirs(category_dir, exist_ok=True)

    # 生成唯一文件名
    ext = file.filename.split(".")[-1]
    filename = f"{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(category_dir, filename)

    # 3. 写入磁盘
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail="文件写入失败")

    # 4. 生成 URL (相对路径)
    # 格式: /static/category/filename
    url = f"/static/{category}/{filename}"

    # 5. 存入图片库数据库
    image_id = db.execute(
        "INSERT INTO images (user_id, url, filename, category) VALUES (?, ?, ?, ?)",
        (user_id, url, file.filename, category)
    )

    return {
        "status": "success",
        "image": {
            "id": image_id,
            "url": url,
            "category": category
        }
    }


@router.get("/list")
def get_my_images(category: str = None, current_user: dict = Depends(get_current_user)):
    user_id = current_user['id']

    sql = "SELECT id, url, category, created_at FROM images WHERE user_id = ?"
    params = [user_id]

    if category:
        sql += " AND category = ?"
        params.append(category)

    sql += " ORDER BY id DESC"

    rows = db.fetch_all(sql, tuple(params))

    return [
        {"id": r[0], "url": r[1], "category": r[2], "created_at": r[3]}
        for r in rows
    ]