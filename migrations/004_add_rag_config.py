# migrations/004_add_rag_config.py
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
        # 创建 rag_config 表
        # id=1 固定存那一条配置即可
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rag_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                mode TEXT DEFAULT 'local',  -- 'online' or 'local'

                -- Online Config
                provider TEXT DEFAULT 'openai',
                api_key TEXT,
                base_url TEXT,
                online_model_name TEXT DEFAULT 'text-embedding-3-small',

                -- Local Config
                local_model_path TEXT DEFAULT 'shibing624/text2vec-base-chinese',

                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 初始化一条默认数据
        cursor.execute("INSERT OR IGNORE INTO rag_config (id, mode) VALUES (1, 'local')")

        print("✅ [Success] 'rag_config' 表已创建。")

    except Exception as e:
        print(f"❌ 迁移失败: {e}")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_db()