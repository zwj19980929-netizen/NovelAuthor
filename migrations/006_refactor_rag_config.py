# migrations/006_rag_multi_row.py
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
        print("正在重构 rag_config 表结构...")

        # 1. 备份旧数据 (如果表存在)
        old_data = []
        try:
            cursor.execute("SELECT user_id, mode, provider, api_key, base_url, online_model_name, local_model_path FROM rag_config")
            old_data = cursor.fetchall()
        except:
            print("⚠️ 旧表可能不存在或结构不兼容，跳过备份。")

        # 2. 删除旧表
        cursor.execute("DROP TABLE IF EXISTS rag_config")

        # 3. 创建新表 (增加 id 主键, is_active 字段)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rag_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,

                -- 配置名称 (可选，方便用户区分)
                name TEXT DEFAULT '默认配置',

                mode TEXT DEFAULT 'local',  -- 'online' or 'local'

                -- Online Config
                provider TEXT DEFAULT 'openai',
                api_key TEXT,
                base_url TEXT,
                online_model_name TEXT DEFAULT 'text-embedding-3-small',

                -- Local Config
                local_model_path TEXT DEFAULT 'shibing624/text2vec-base-chinese',

                is_active BOOLEAN DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # 4. 恢复旧数据 (将旧数据作为默认激活的配置插入)
        if old_data:
            print(f"🔄 正在迁移 {len(old_data)} 条旧配置...")
            for row in old_data:
                # row: user_id, mode, provider, api_key, base_url, online_model_name, local_model_path
                cursor.execute("""
                    INSERT INTO rag_config 
                    (user_id, name, mode, provider, api_key, base_url, online_model_name, local_model_path, is_active)
                    VALUES (?, '旧配置迁移', ?, ?, ?, ?, ?, ?, 1)
                """, row)

        print("✅ [Success] 'rag_config' 表已升级为多配置列表模式。")

    except Exception as e:
        print(f"❌ 迁移失败: {e}")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    upgrade_db()