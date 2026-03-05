# migrations/007_add_project_chapters.py
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
        # 给 projects 表添加 total_chapters 字段，默认值为 20
        cursor.execute("ALTER TABLE projects ADD COLUMN total_chapters INTEGER DEFAULT 20")
        print("✅ [Success] 'total_chapters' 字段已添加到 projects 表。")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e):
            print("⚠️ [Skip] 'total_chapters' 字段已存在。")
        else:
            print(f"❌ [Error] 添加字段失败: {e}")

    conn.commit()
    conn.close()
    print("✨ 数据库迁移完成。")

if __name__ == "__main__":
    upgrade_db()