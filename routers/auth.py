# routers/auth.py
import os
import uuid
import shutil
import random
import string
from datetime import timedelta, datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from db.manager import db
from utils.security import (
    verify_password, get_password_hash, create_access_token,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from utils.deps import get_current_user
from utils.email_sender import send_verification_email

router = APIRouter(prefix="/auth", tags=["Auth"])


# --- Models ---

class Token(BaseModel):
    access_token: str
    token_type: str
    user_info: dict


class UserRegister(BaseModel):
    username: str
    password: str
    nickname: str
    email: str = ""
    code: str = ""


class UpdateProfileRequest(BaseModel):
    nickname: str
    email: Optional[str] = None
    avatar: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


# 🔥 新增：找回密码请求模型
class ForgotPasswordSendCodeRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str


# --- Helper ---
def generate_code(length=6):
    return ''.join(random.choices(string.digits, k=length))


# --- Endpoints ---

@router.post("/register")
def register(user: UserRegister):
    # 1. 检查用户名
    if db.fetch_one("SELECT id FROM users WHERE username = ?", (user.username,)):
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 2. 校验验证码 (如果有 email)
    if user.email:
        row = db.fetch_one("SELECT code FROM verification_codes WHERE email = ?", (user.email,))
        if not row or row[0] != user.code:
            raise HTTPException(status_code=400, detail="验证码错误或已过期")
        # 验证通过后删除验证码
        db.execute("DELETE FROM verification_codes WHERE email = ?", (user.email,))

    hashed_pw = get_password_hash(user.password)

    try:
        user_id = db.execute(
            "INSERT INTO users (username, hashed_password, nickname, email, created_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (user.username, hashed_pw, user.nickname, user.email)
        )

        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.username, "uid": user_id}, expires_delta=access_token_expires
        )

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user_info": {
                "id": user_id,
                "username": user.username,
                "nickname": user.nickname,
                "avatar": None
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/token", response_model=Token)
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = db.fetch_one("SELECT id, username, hashed_password, nickname, avatar FROM users WHERE username = ?", (form_data.username,))

    if not user or not verify_password(form_data.password, user[2]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user[1], "uid": user[0]}, expires_delta=access_token_expires
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_info": {
            "id": user[0],
            "username": user[1],
            "nickname": user[3],
            "avatar": user[4]
        }
    }


@router.post("/send-code")
def send_verification_code(payload: dict):
    email = payload.get('email')
    if not email:
        raise HTTPException(status_code=400, detail="邮箱不能为空")

    code = generate_code()

    # 存入数据库 (REPLACE INTO 会覆盖旧的)
    db.execute("REPLACE INTO verification_codes (email, code, created_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (email, code))

    # 发送邮件
    try:
        send_verification_email(email, code)
    except Exception as e:
        print(f"Send mail failed: {e}")
        raise HTTPException(status_code=500, detail="邮件发送失败，请检查服务器配置")

    return {"status": "sent", "message": "验证码已发送"}


# 🔥 新增：忘记密码 - 发送验证码
@router.post("/forgot-password/send-code")
def forgot_password_send_code(req: ForgotPasswordSendCodeRequest):
    # 1. 检查邮箱是否存在
    user = db.fetch_one("SELECT id FROM users WHERE email = ?", (req.email,))
    if not user:
        raise HTTPException(status_code=404, detail="该邮箱未注册")

    # 2. 生成验证码
    code = generate_code()

    # 3. 存库
    db.execute("REPLACE INTO verification_codes (email, code, created_at) VALUES (?, ?, CURRENT_TIMESTAMP)", (req.email, code))

    # 4. 发送
    try:
        send_verification_email(req.email, code)
    except Exception as e:
        print(f"Forgot PW Mail Error: {e}")
        raise HTTPException(status_code=500, detail="邮件发送失败")

    return {"status": "success", "message": "验证码已发送至您的邮箱"}


# 🔥 新增：忘记密码 - 重置密码
@router.post("/forgot-password/reset")
def reset_password(req: ResetPasswordRequest):
    # 1. 校验验证码
    row = db.fetch_one("SELECT code FROM verification_codes WHERE email = ?", (req.email,))
    if not row or row[0] != req.code:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    # 2. 更新密码
    new_hash = get_password_hash(req.new_password)
    db.execute("UPDATE users SET hashed_password = ? WHERE email = ?", (new_hash, req.email))

    # 3. 销毁验证码
    db.execute("DELETE FROM verification_codes WHERE email = ?", (req.email,))

    return {"status": "success", "message": "密码重置成功，请使用新密码登录"}


@router.post("/upload-avatar")
async def upload_avatar(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    user_id = current_user['id']

    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="只能上传图片文件")

    ext = file.filename.split(".")[-1]
    filename = f"user_{user_id}_{uuid.uuid4().hex[:8]}.{ext}"

    save_dir = "uploads/avatars"
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    file_path = os.path.join(save_dir, filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    avatar_url = f"/static/avatars/{filename}"
    db.execute("UPDATE users SET avatar = ? WHERE id = ?", (avatar_url, user_id))

    return {"status": "success", "url": avatar_url}


@router.post("/update-profile")
def update_profile(req: UpdateProfileRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user['id']
    try:
        fields = ["nickname = ?"]
        values = [req.nickname]

        if req.email is not None:
            fields.append("email = ?")
            values.append(req.email)

        if req.avatar is not None:
            fields.append("avatar = ?")
            values.append(req.avatar)

        values.append(user_id)

        sql = f"UPDATE users SET {', '.join(fields)} WHERE id = ?"
        db.execute(sql, tuple(values))

        updated_user = db.fetch_one("SELECT id, username, nickname, avatar, email FROM users WHERE id = ?", (user_id,))
        return {
            "status": "success",
            "user_info": {
                "id": updated_user[0],
                "username": updated_user[1],
                "nickname": updated_user[2],
                "avatar": updated_user[3],
                "email": updated_user[4]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/change-password")
def change_password(req: ChangePasswordRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user['id']

    row = db.fetch_one("SELECT hashed_password FROM users WHERE id = ?", (user_id,))
    if not row or not verify_password(req.old_password, row[0]):
        raise HTTPException(status_code=400, detail="旧密码错误")

    new_hash = get_password_hash(req.new_password)
    db.execute("UPDATE users SET hashed_password = ? WHERE id = ?", (new_hash, user_id))

    return {"status": "success", "message": "密码修改成功，请重新登录"}