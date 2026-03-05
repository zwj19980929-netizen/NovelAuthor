# utils/deps.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from utils.security import SECRET_KEY, ALGORITHM
from db.manager import db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user_id: int = payload.get("uid")
        if username is None or user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # 🔥 顺便查一下昵称
    row = db.fetch_one("SELECT nickname FROM users WHERE id = ?", (user_id,))
    nickname = row[0] if row else username

    return {"id": user_id, "username": username, "nickname": nickname}