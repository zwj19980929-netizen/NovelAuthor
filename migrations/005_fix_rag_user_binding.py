# migrations/005_fix_rag_user_binding.py
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
        # 1. 如果表已存在，我们先删掉重建 (开发环境暴力一点没关系，或者你可以写 ALTER TABLE)
        # 为了确保结构正确，这里建议先重置这个表
        cursor.execute("DROP TABLE IF EXISTS rag_config")

        # 2. 重新创建，主键改为 user_id (不再是固定为1)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rag_config (
                user_id INTEGER PRIMARY KEY, -- 🔥 核心修改：绑定到用户
                mode TEXT DEFAULT 'local',  -- 'online' or 'local'

                -- Online Config
                provider TEXT DEFAULT 'openai',
                api_key TEXT,
                base_url TEXT,
                online_model_name TEXT DEFAULT 'text-embedding-3-small',

                -- Local Config
                local_model_path TEXT DEFAULT 'shibing624/text2vec-base-chinese',

                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        print("✅ [Success] 'rag_config' 表已重构为多用户模式。")

    except Exception as e:
        print(f"❌ 迁移失败: {e}")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_db()