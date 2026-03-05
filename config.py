# config.py
import os

# 数据库路径
DB_PATH = "trinity.db"

# JWT配置
# 🔥 核心修复 1：把这串字符固定死！绝对不要用 random 生成，也不要留空。
# 只要这串字符不变，服务器重启多少次，你的 Token 都依然有效。
SECRET_KEY = "TRINITY_AI_FIXED_DEV_KEY_2024"

ALGORITHM = "HS256"

# 🔥 核心修复 2：有效期设长一点，比如 7 天 (60 * 24 * 7)
ACCESS_TOKEN_EXPIRE_MINUTES = 10080

# 邮件服务配置 (请保持你自己填好的真实信息，不要被我覆盖了)
SMTP_CONFIG = {
    "SERVER": "smtp.qq.com",
    "PORT": 465,
    "USER": "318443211@qq.com", # <--- 记得确认这里是你自己的邮箱
    "PASSWORD": "kvholszwcigvcaij", # <--- 记得填回你的授权码
    "USE_SSL": True
}

# 加密存储用的 Key (用于加密 API Key 等敏感信息)
# 这个 Key 也需要固定，否则重启后数据库里的 API Key 就解不开了
# 这里我们硬编码一个固定的 Key 用于开发环境
APP_ENCRYPTION_KEY = b'gQjXwY7lKz9_p0mN3sR5vA8dE2tH6yJ1oU4iF9cB0aZ='

# 设置环境变量，供 utils/encryption.py 读取
os.environ["APP_ENCRYPTION_KEY"] = APP_ENCRYPTION_KEY.decode()