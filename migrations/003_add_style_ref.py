# migrations/003_add_style_ref.py
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
        # 1. 创建样章表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS style_references (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                content TEXT NOT NULL, -- 样章正文
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        print("✅ [Success] 'style_references' 表已创建。")

        # 2. 给 projects 表添加 style_ref_id
        try:
            cursor.execute("ALTER TABLE projects ADD COLUMN style_ref_id INTEGER REFERENCES style_references(id)")
            print("✅ [Success] 'style_ref_id' 字段已添加到 projects 表。")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e):
                print("⚠️ [Skip] 'style_ref_id' 字段已存在。")
            else:
                print(f"❌ [Error] 添加字段失败: {e}")

    except Exception as e:
        print(f"❌ 迁移失败: {e}")

    conn.commit()
    conn.close()
    print("✨ 样章系统数据库升级完成。")

if __name__ == "__main__":
    upgrade_db()