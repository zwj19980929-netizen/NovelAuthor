# migrations/009_upgrade_author_system.py
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
        # 1. 升级 author_presets 表，增加状态字段
        try:
            cursor.execute("ALTER TABLE author_presets ADD COLUMN status TEXT DEFAULT 'completed'")
            print("✅ [Success] 'status' 字段已添加到 author_presets。")
        except Exception as e:
            print(f"ℹ️ author_presets.status 可能已存在: {e}")

        # 2. 升级 style_references 表，增加关联字段
        try:
            cursor.execute("ALTER TABLE style_references ADD COLUMN author_preset_id INTEGER REFERENCES author_presets(id) ON DELETE CASCADE")
            print("✅ [Success] 'author_preset_id' 字段已添加到 style_references。")
        except Exception as e:
            print(f"ℹ️ style_references.author_preset_id 可能已存在: {e}")

    except Exception as e:
        print(f"❌ 迁移失败: {e}")

    conn.commit()
    conn.close()
    print("✨ 作者系统数据库升级完成。")

if __name__ == "__main__":
    upgrade_db()