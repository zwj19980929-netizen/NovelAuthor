# migrations/008_add_author_presets.py
import sqlite3
import sys
import os

# 路径适配
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
        # 创建 author_presets 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS author_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                author_name TEXT NOT NULL,
                style_profile TEXT, -- AI 分析生成的风格画像
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        print("✅ [Success] 'author_presets' 表已创建。")

        # 为了方便，我们在 projects 表加一个字段记录用了哪个作者（可选，主要用于回显）
        try:
            cursor.execute("ALTER TABLE projects ADD COLUMN author_preset_id INTEGER REFERENCES author_presets(id)")
            print("✅ [Success] 'author_preset_id' 字段已添加到 projects 表。")
        except:
            pass

    except Exception as e:
        print(f"❌ 迁移失败: {e}")

    conn.commit()
    conn.close()
    print("✨ 作者库架构升级完成。")

if __name__ == "__main__":
    upgrade_db()