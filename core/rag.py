# core/rag.py
import chromadb
from chromadb.config import Settings
import os
import re
from utils.embedding_factory import EmbeddingFactory

# 存储路径
CHROMA_PATH = os.path.join(os.getcwd(), "chroma_db")


class RAGManager:
    """项目剧情记忆检索 (Project Memory)"""

    def __init__(self, project_id: int, user_id: int):
        self.project_id = str(project_id)
        self.user_id = user_id
        self.client = chromadb.PersistentClient(path=CHROMA_PATH)
        self.emb_fn = EmbeddingFactory.get_embedding_function(self.user_id)
        self.collection = self.client.get_or_create_collection(
            name=f"project_{self.project_id}_memory",
            embedding_function=self.emb_fn
        )

    def add_chapter(self, chapter_num: int, title: str, content: str):
        chunk_size = 500
        overlap = 50
        chunks = []
        text = re.sub(r'\n+', '\n', content)
        for i in range(0, len(text), chunk_size - overlap):
            chunk = text[i: i + chunk_size]
            if len(chunk) > 50:
                chunks.append(chunk)
        if not chunks: return

        ids = [f"ch{chapter_num}_{i}" for i in range(len(chunks))]
        metadatas = [{"chapter": chapter_num, "title": title} for _ in chunks]

        try:
            existing = self.collection.get(where={"chapter": chapter_num})
            if existing and existing['ids']:
                self.collection.delete(ids=existing['ids'])
        except Exception as e:
            print(f"RAG Clean Error: {e}")

        self.collection.add(documents=chunks, metadatas=metadatas, ids=ids)
        print(f"🧠 [RAG] 已索引第 {chapter_num} 章，共 {len(chunks)} 个记忆碎片。")

    def search(self, query: str, n_results: int = 3) -> str:
        if not query or len(query) < 2: return ""
        try:
            results = self.collection.query(query_texts=[query], n_results=n_results)
            if not results['documents'] or not results['documents'][0]:
                return "无相关历史记录。"

            context_pieces = []
            for i, doc in enumerate(results['documents'][0]):
                meta = results['metadatas'][0][i]
                source = f"[回顾: 第{meta['chapter']}章 {meta['title']}]"
                context_pieces.append(f"{source}\n{doc}")
            return "\n\n".join(context_pieces)
        except Exception as e:
            print(f"⚠️ RAG Search Error: {e}")
            return ""

    def count(self):
        return self.collection.count()


class StyleRAGManager:
    """🔥 新增：作者风格检索 (Author Style RAG)"""

    def __init__(self, user_id: int):
        self.user_id = user_id
        self.client = chromadb.PersistentClient(path=CHROMA_PATH)
        self.emb_fn = EmbeddingFactory.get_embedding_function(self.user_id)

        # 这是一个全局集合，我们在 metadata 里区分 author_id
        self.collection = self.client.get_or_create_collection(
            name=f"user_{self.user_id}_styles",
            embedding_function=self.emb_fn
        )

    def add_sample(self, sample_id: int, author_id: int, content: str, title: str):
        """添加或更新例章到向量库"""
        # 先删除旧的 (如果存在)
        try:
            self.collection.delete(ids=[str(sample_id)])
        except:
            pass

        # 存入
        self.collection.add(
            ids=[str(sample_id)],
            documents=[content],
            metadatas=[{"author_id": author_id, "title": title}]
        )
        print(f"✒️ [StyleRAG] 已索引例章: {title}")

    def delete_sample(self, sample_id: int):
        try:
            self.collection.delete(ids=[str(sample_id)])
        except:
            pass

    def search_relevant_style(self, author_id: int, query: str, n_results: int = 1) -> str:
        """
        根据当前剧情 (query)，在指定作者 (author_id) 的库里找最相似的写法
        """
        if not query: return ""

        try:
            # 🔥 核心：只在当前作者的范围内搜索 (where 过滤)
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where={"author_id": author_id}
            )

            if not results['documents'] or not results['documents'][0]:
                return ""  # 没找到相关例章，返回空，让 Writer 自己发挥

            # 找到了，返回内容
            best_match = results['documents'][0][0]
            best_title = results['metadatas'][0][0]['title']

            # 这里可以加一个距离阈值判断，如果距离太远说明完全不相关，也可以返回空
            # 但目前先假定“最相关”的就是最好的参考

            return f"【参考范例：{best_title}】\n{best_match}"

        except Exception as e:
            print(f"Style Search Error: {e}")
            return ""