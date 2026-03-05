# utils/llm_provider.py
import json
import os
import re
from abc import ABC, abstractmethod
from openai import OpenAI
import qianfan
from db.manager import db
from utils.encryption import decrypt_value


def _clean_url(url: str) -> str:
    if not url: return ""
    url = url.strip()
    match = re.search(r'\((https?://.*?)\)', url)
    if match: return match.group(1)
    return url.replace('[', '').replace(']', '')


def _extract_json(text: str) -> str:
    text = text.strip()
    code_block_pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
    match = re.search(code_block_pattern, text, re.DOTALL)
    if match: return match.group(1)
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        return text[start: end + 1]
    return text


class BaseLLM(ABC):
    def __init__(self, api_key, model_name, base_url=None, secret_key=None, provider="unknown"):
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = _clean_url(base_url)
        self.secret_key = secret_key
        self.provider = provider

        if not self.base_url:
            if self.provider == "deepseek":
                self.base_url = "https://api.deepseek.com/v1"
            elif self.provider == "openai":
                self.base_url = "https://api.openai.com/v1"
            elif self.provider == "tongyi":
                self.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            elif self.provider == "gemini":
                self.base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"

    @abstractmethod
    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        pass

    # 🔥 新增：流式生成接口
    @abstractmethod
    def stream_text(self, system_prompt: str, user_prompt: str):
        """返回一个生成器，逐个 yield 字符/片段"""
        pass

    def generate_json(self, system_prompt: str, user_prompt: str, pydantic_model=None, max_retries=2) -> dict:
        prompt_suffix = "\n请务必输出严格的纯 JSON 格式，不要包含任何解释性文字或 Markdown 标记。"
        if pydantic_model:
            schema = pydantic_model.model_json_schema()
            prompt_suffix += f"\n请严格遵守以下 JSON Schema:\n{json.dumps(schema, ensure_ascii=False)}"

        full_user_prompt = user_prompt + prompt_suffix

        for attempt in range(max_retries + 1):
            try:
                response_text = self.generate_text(system_prompt, full_user_prompt)
                clean_text = _extract_json(response_text)
                data = json.loads(clean_text)
                if pydantic_model:
                    return pydantic_model(**data)
                return data
            except (json.JSONDecodeError, Exception) as e:
                print(f"⚠️ JSON Parse Error (Attempt {attempt + 1}): {e}")
                if attempt == max_retries:
                    return {}
                else:
                    full_user_prompt += f"\n\n❌ 上次生成的 JSON 格式有误，请重新生成。"
        return {}


class OpenAILLM(BaseLLM):
    def __init__(self, api_key, model_name, base_url=None, provider="openai", **kwargs):
        super().__init__(api_key, model_name, base_url, provider=provider)
        print(f"🔗 Connecting to: {self.base_url} (Model: {self.model_name})")
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"❌ OpenAI/Compatible API Error: {e}")
            raise e

    # 🔥 新增：实现流式
    def stream_text(self, system_prompt: str, user_prompt: str):
        try:
            stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                stream=True # 开启流式
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            print(f"❌ Stream Error: {e}")
            yield f"[Error: {str(e)}]"


class WenxinLLM(BaseLLM):
    def __init__(self, api_key, model_name, secret_key=None, provider="wenxin", **kwargs):
        super().__init__(api_key, model_name, secret_key=secret_key, provider=provider)
        os.environ["QIANFAN_ACCESS_KEY"] = self.api_key
        os.environ["QIANFAN_SECRET_KEY"] = self.secret_key

    def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        chat_comp = qianfan.ChatCompletion()
        try:
            resp = chat_comp.do(
                model=self.model_name,
                messages=[{"role": "user", "content": user_prompt}],
                system=system_prompt
            )
            return resp["body"]["result"]
        except Exception as e:
            print(f"Wenxin API Error: {e}")
            raise e

    # 🔥 文心流式支持
    def stream_text(self, system_prompt: str, user_prompt: str):
        chat_comp = qianfan.ChatCompletion()
        try:
            resp = chat_comp.do(
                model=self.model_name,
                messages=[{"role": "user", "content": user_prompt}],
                system=system_prompt,
                stream=True
            )
            for r in resp:
                yield r["body"]["result"]
        except Exception as e:
            yield f"[Error: {e}]"


class LLMFactory:
    @staticmethod
    def create(project_id: int = None, user_id: int = None, role: str = "writer"):
        """
        创建 LLM 实例。
        逻辑优先级:
        1. 如果有 project_id -> 从 projects 表读取该项目绑定的模型 (用于写书/大纲)。
        2. 如果无 project_id 但有 user_id -> 从 user_settings 表读取全局偏好 (用于作者分析、全局工具)。
        3. 如果上述都未配置 -> 使用 llm_credentials 中 is_active=1 的默认模型。
        """
        provider = None
        api_key_enc = None
        base_url = None
        model_name = None
        secret_key_enc = None
        target_cred_id = None

        # ------------------------------------------------------------------
        # 场景 A: 项目上下文 (Writing, Planning within a Project)
        # ------------------------------------------------------------------
        if project_id:
            proj = db.fetch_one("SELECT user_id, llm_credential_id, writer_credential_id FROM projects WHERE id = ?", (project_id,))
            if proj:
                fetched_user_id, main_cred_id, writer_cred_id = proj
                # 如果调用方没传 user_id，使用项目所属用户的
                if not user_id:
                    user_id = fetched_user_id

                # 根据角色决定使用哪个配置
                if role == 'writer':
                    target_cred_id = writer_cred_id
                else:
                    # architect, author (in project context), etc.
                    target_cred_id = main_cred_id

                    # ------------------------------------------------------------------
        # 场景 B: 全局上下文 (Author Analysis, Tools outside Project)
        # ------------------------------------------------------------------
        # 如果没有找到 target_cred_id (说明不是项目内，或者项目没配)，且有 user_id
        if not target_cred_id and user_id:
            # 读取用户的全局偏好设置
            setting_row = db.fetch_one("SELECT config_json FROM user_settings WHERE user_id = ?", (user_id,))
            if setting_row and setting_row[0]:
                try:
                    config = json.loads(setting_row[0])
                    # 根据角色查找对应的 model_id
                    if role == 'architect':
                        target_cred_id = config.get('architect_model_id')
                    elif role == 'writer':
                        target_cred_id = config.get('writer_model_id')
                    elif role == 'author':  # 🔥 新增：作者分析专用
                        target_cred_id = config.get('author_model_id')
                except:
                    pass

        # ------------------------------------------------------------------
        # 3. 获取凭证详情 (Resolve Credential)
        # ------------------------------------------------------------------

        # 尝试 1: 如果找到了特定的 ID，尝试获取该 ID 的凭证
        if target_cred_id:
            cred = db.fetch_one(
                "SELECT provider, api_key_enc, secret_key_enc, base_url, model_name FROM llm_credentials WHERE id = ?",
                (target_cred_id,)
            )
            if cred:
                provider, api_key_enc, secret_key_enc, base_url, model_name = cred

        # 尝试 2: 兜底 (如果没有指定 ID，或指定的 ID 被删了)，取 is_active=1 的默认值
        if not provider and user_id:
            cred = db.fetch_one(
                "SELECT provider, api_key_enc, secret_key_enc, base_url, model_name FROM llm_credentials WHERE user_id = ? AND is_active = 1 LIMIT 1",
                (user_id,)
            )
            if cred:
                provider, api_key_enc, secret_key_enc, base_url, model_name = cred

        # ------------------------------------------------------------------
        # 4. 实例化 (Instantiation)
        # ------------------------------------------------------------------
        api_key = decrypt_value(api_key_enc)
        secret_key = decrypt_value(secret_key_enc) if secret_key_enc else None

        if not api_key:
            error_msg = f"❌ [配置缺失] 未找到可用的 API Key (User: {user_id}, Role: {role})。请在【系统设置】中配置智能矩阵或激活默认模型。"
            print(error_msg)
            raise ValueError(error_msg)

        print(f"🔌 Using LLM [{role}]: {provider} ({model_name})")

        if provider in ["openai", "deepseek", "tongyi", "gemini"]:
            return OpenAILLM(api_key, model_name, base_url, provider=provider)
        elif provider == "wenxin":
            return WenxinLLM(api_key, model_name, secret_key=secret_key, provider=provider)
        else:
            return OpenAILLM(api_key, model_name, base_url, provider=provider)