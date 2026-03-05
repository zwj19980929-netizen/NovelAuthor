# utils/embedding_factory.py
import os
from chromadb.utils import embedding_functions
from db.manager import db


class EmbeddingFactory:
    @staticmethod
    def _create_function(mode, provider, api_key, base_url, online_name, local_path):
        """
        内部方法：根据参数创建 embedding function 实例
        """
        print(f"🔌 [Embedding Factory] 加载模式: {mode}")

        # 1. 在线模式 (OpenAI / DeepSeek 等)
        if mode == 'online':
            if not api_key:
                print("⚠️ [RAG] 在线模式未配置 API Key，回退到本地模式。")
                return embedding_functions.SentenceTransformerEmbeddingFunction(model_name=local_path)

            print(f"   -> Provider: {provider} | Model: {online_name}")
            return embedding_functions.OpenAIEmbeddingFunction(
                api_key=api_key,
                api_base=base_url if base_url else None,
                model_name=online_name
            )

        # 2. 本地模式 (HuggingFace / SentenceTransformer)
        else:
            print(f"   -> Local Path: {local_path}")
            return embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=local_path
            )

    @staticmethod
    def get_embedding_function(user_id: int):
        """
        工厂方法：根据指定用户的【已激活】配置，动态生成 Embedding 函数
        """
        # 🔥 修改：查询 is_active = 1 的配置
        row = db.fetch_one(
            "SELECT mode, provider, api_key, base_url, online_model_name, local_model_path FROM rag_config WHERE user_id = ? AND is_active = 1",
            (user_id,)
        )

        # 默认兜底
        if not row:
            mode = 'local'
            local_path = "shibing624/text2vec-base-chinese"
            provider = api_key = base_url = online_name = None
        else:
            mode, provider, api_key, base_url, online_name, local_path = row

        return EmbeddingFactory._create_function(mode, provider, api_key, base_url, online_name, local_path)

    @staticmethod
    def create_for_test(config: dict):
        """
        测试用：不读数据库，直接根据前端传来的 config 字典创建
        """
        return EmbeddingFactory._create_function(
            mode=config.get('mode', 'local'),
            provider=config.get('provider', 'openai'),
            api_key=config.get('api_key', ''),
            base_url=config.get('base_url', ''),
            online_name=config.get('online_model_name', ''),
            local_path=config.get('local_model_path', '')
        )