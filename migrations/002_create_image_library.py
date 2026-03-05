import sqlite3
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from config import DB_PATH

if not os.path.isabs(DB_PATH):
    REAL_DB_PATH = os.path.join(parent_dir, DB_PATH)
else:
    REAL_DB_PATH = DB_PATH


def upgrade_db():
    print(f"📡 正在连接数据库: {REAL_DB_PATH}")
    conn = sqlite3.connect(REAL_DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. 创建 images 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                url TEXT NOT NULL,
                filename TEXT,
                category TEXT DEFAULT 'general', -- avatar, cover, general
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✅ [Success] 'images' 表已创建。")

        # 2. 确保 users 表有 avatar 字段 (防止上一步没做)
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN avatar TEXT")
            print("✅ [Success] 'avatar' 字段已补全。")
        except:
            print("⚠️ 'avatar' 字段已存在。")

    except Exception as e:
        print(f"❌ 迁移失败: {e}")

    conn.commit()
    conn.close()
    print("✨ 图片库架构升级完成。")


if __name__ == "__main__":
    upgrade_db()