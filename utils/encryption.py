# utils/encryption.py
from cryptography.fernet import Fernet
import os
import base64

# ⚠️ 生产环境请固定这个 Key，否则重启后旧数据无法解密
# 这里我们硬编码一个开发用的 Key
_DEV_KEY = b'gQjXwY7lKz9_p0mN3sR5vA8dE2tH6yJ1oU4iF9cB0aZ='
ENCRYPTION_KEY = os.getenv("APP_ENCRYPTION_KEY", _DEV_KEY.decode()).encode()

cipher = Fernet(ENCRYPTION_KEY)

def encrypt_value(value: str) -> str:
    """加密敏感信息"""
    if not value: return ""
    try:
        return cipher.encrypt(value.encode()).decode()
    except Exception as e:
        print(f"Encryption Error: {e}")
        return ""

def decrypt_value(token: str) -> str:
    """解密敏感信息"""
    if not token: return ""
    try:
        return cipher.decrypt(token.encode()).decode()
    except Exception:
        return "[Decryption Failed]"