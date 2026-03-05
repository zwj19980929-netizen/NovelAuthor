# migrations/001_add_character_fields.py
import sqlite3
import sys
import os

# 1. 把父目录加入系统路径，以便导入 config.py
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from config import DB_PATH

# 2. 修正数据库路径 (因为 DB_PATH 可能是相对路径 "trinity.db")
# 我们需要确保它指向的是父目录下的那个 db 文件
if not os.path.isabs(DB_PATH):
    REAL_DB_PATH = os.path.join(parent_dir, DB_PATH)
else:
    REAL_DB_PATH = DB_PATH


def upgrade_db():
    print(f"📡 正在连接数据库: {REAL_DB_PATH}")
    conn = sqlite3.connect(REAL_DB_PATH)
    cursor = conn.cursor()

    # === 任务 1: 添加 role (角色定位) 字段 ===
    try:
        cursor.execute("ALTER TABLE characters ADD COLUMN role TEXT DEFAULT '配角'")
        print("✅ [Success] 'role' 字段已添加。")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("⚠️ [Skip] 'role' 字段已存在。")
        else:
            print(f"❌ [Error] 添加 role 失败: {e}")

    # === 任务 2: 检查 target 和 fear ===
    # 注意：这两个字段是存在 core_vector (JSON) 里的，不需要改表结构。
    # 但我们可以打印一下当前的 JSON 数据看看
    try:
        cursor.execute("SELECT id, name, core_vector FROM characters LIMIT 5")
        rows = cursor.fetchall()
        print(f"ℹ️ [Info] 当前前 5 个角色的数据预览: ")
        for r in rows:
            print(f"   - ID {r[0]} ({r[1]}): {r[2]}")
    except Exception as e:
        print(f"❌ [Error] 读取数据失败: {e}")

    conn.commit()
    conn.close()
    print("✨ 数据库迁移脚本执行完毕。")


if __name__ == "__main__":
    upgrade_db()