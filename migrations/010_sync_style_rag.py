# migrations/010_sync_style_rag.py
import sqlite3
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

from config import DB_PATH
from core.rag import StyleRAGManager

if not os.path.isabs(DB_PATH):
    REAL_DB_PATH = os.path.join(parent_dir, DB_PATH)
else:
    REAL_DB_PATH = DB_PATH


def sync_data():
    print(f"📡 正在连接数据库: {REAL_DB_PATH}")
    conn = sqlite3.connect(REAL_DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. 查出所有绑定了 author_preset_id 的例章
        cursor.execute("SELECT id, user_id, name, content, author_preset_id FROM style_references WHERE author_preset_id IS NOT NULL")
        rows = cursor.fetchall()

        print(f"🔄 发现 {len(rows)} 条例章，准备同步到 Chroma 向量库...")

        for r in rows:
            sample_id = r[0]
            user_id = r[1]
            title = r[2]
            content = r[3]
            author_id = r[4]

            if not content or len(content) < 10:
                print(f"   ⚠️ 跳过空内容: {title}")
                continue

            try:
                # 初始化该用户的 RAG 管理器
                rag = StyleRAGManager(user_id)
                # 索引
                rag.add_sample(sample_id, author_id, content, title)
                # print(f"   ✅ 已索引: {title}")
            except Exception as e:
                print(f"   ❌ 索引失败 {title}: {e}")

        print("✨ 所有例章已同步完成！")

    except Exception as e:
        print(f"❌ 同步过程出错: {e}")

    conn.close()


if __name__ == "__main__":
    sync_data()