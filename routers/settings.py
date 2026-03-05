# routers/settings.py
import json
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from db.manager import db
from utils.deps import get_current_user
from utils.encryption import encrypt_value
from utils.llm_provider import OpenAILLM, WenxinLLM, LLMFactory
from utils.embedding_factory import EmbeddingFactory  # 🔥 引入新工厂方法

router = APIRouter(prefix="/settings", tags=["Settings"])


# --- Models ---

class CredentialCreate(BaseModel):
    provider: str
    api_key: str
    secret_key: str = ""
    base_url: str = ""
    model_name: str

    model_config = ConfigDict(protected_namespaces=())


class CredentialUpdate(BaseModel):
    provider: Optional[str] = None
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    base_url: Optional[str] = None
    model_name: Optional[str] = None

    model_config = ConfigDict(protected_namespaces=())


class PreferencesUpdate(BaseModel):
    architect_model_id: Optional[int] = None
    writer_model_id: Optional[int] = None
    author_model_id: Optional[int] = None  # 🔥 新增：作者分析专用模型ID
    temperature: float = 0.8
    context_window: int = 10
    target_word_count: int = 2000
    total_chapters: int = 20
    narrative_view: str = 'third'
    auto_save: bool = True


# 🔥 RAG 配置模型 (更新)
class RagConfigCreate(BaseModel):
    name: str = "新配置"
    mode: str  # 'online' or 'local'
    provider: Optional[str] = 'openai'
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    online_model_name: Optional[str] = 'text-embedding-3-small'
    local_model_path: Optional[str] = 'shibing624/text2vec-base-chinese'


class RagConfigUpdate(RagConfigCreate):
    pass


# --- Endpoints: Credentials (LLM 凭证管理) ---

@router.post("/credentials")
def save_credential(req: CredentialCreate, current_user: dict = Depends(get_current_user)):
    user_id = current_user['id']

    existing = db.fetch_one(
        "SELECT id FROM llm_credentials WHERE user_id = ? AND provider = ? AND model_name = ?",
        (user_id, req.provider, req.model_name)
    )

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"您已添加过 [{req.provider}] 的 {req.model_name} 模型，请勿重复添加。"
        )

    key_enc = encrypt_value(req.api_key)
    sec_enc = encrypt_value(req.secret_key) if req.secret_key else None

    clean_url = req.base_url
    if clean_url and "(" in clean_url and ")" in clean_url:
        try:
            clean_url = clean_url.split("](")[1].split(")")[0]
        except:
            pass

    db.execute("UPDATE llm_credentials SET is_active = 0 WHERE user_id = ?", (user_id,))

    db.execute(
        """INSERT INTO llm_credentials 
           (user_id, provider, api_key_enc, secret_key_enc, base_url, model_name, is_active)
           VALUES (?, ?, ?, ?, ?, ?, 1)""",
        (user_id, req.provider, key_enc, sec_enc, clean_url, req.model_name)
    )
    return {"status": "success", "message": "配置已保存"}


@router.get("/credentials")
def get_credentials(current_user: dict = Depends(get_current_user)):
    user_id = current_user['id']
    rows = db.fetch_all(
        "SELECT id, provider, model_name, base_url, is_active, created_at FROM llm_credentials WHERE user_id = ? ORDER BY id DESC",
        (user_id,)
    )
    return [
        {
            "id": r[0], "provider": r[1], "model_name": r[2],
            "base_url": r[3], "is_active": bool(r[4]), "created_at": r[5]
        }
        for r in rows
    ]


@router.delete("/credentials/{cred_id}")
def delete_credential(cred_id: int, current_user: dict = Depends(get_current_user)):
    user_id = current_user['id']
    row = db.fetch_one("SELECT id, is_active FROM llm_credentials WHERE id = ? AND user_id = ?", (cred_id, user_id))
    if not row:
        raise HTTPException(status_code=404, detail="凭证不存在")

    db.execute("UPDATE projects SET llm_credential_id = NULL WHERE llm_credential_id = ?", (cred_id,))
    db.execute("UPDATE projects SET writer_credential_id = NULL WHERE writer_credential_id = ?", (cred_id,))

    db.execute("DELETE FROM llm_credentials WHERE id = ?", (cred_id,))

    if row[1]:
        latest = db.fetch_one("SELECT id FROM llm_credentials WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
        if latest:
            db.execute("UPDATE llm_credentials SET is_active = 1 WHERE id = ?", (latest[0],))

    return {"status": "success", "message": "已删除，相关项目已解除绑定"}


@router.post("/credentials/{cred_id}/activate")
def activate_credential(cred_id: int, current_user: dict = Depends(get_current_user)):
    user_id = current_user['id']
    if not db.fetch_one("SELECT id FROM llm_credentials WHERE id = ? AND user_id = ?", (cred_id, user_id)):
        raise HTTPException(status_code=404, detail="凭证不存在")

    db.execute("UPDATE llm_credentials SET is_active = 0 WHERE user_id = ?", (user_id,))
    db.execute("UPDATE llm_credentials SET is_active = 1 WHERE id = ?", (cred_id,))

    return {"status": "success", "message": "已切换默认模型"}


@router.put("/credentials/{cred_id}")
def update_credential(cred_id: int, req: CredentialUpdate, current_user: dict = Depends(get_current_user)):
    user_id = current_user['id']

    current_cred = db.fetch_one("SELECT id, provider, model_name FROM llm_credentials WHERE id = ? AND user_id = ?", (cred_id, user_id))
    if not current_cred:
        raise HTTPException(status_code=404, detail="凭证不存在")

    target_provider = req.provider if req.provider else current_cred[1]
    target_model = req.model_name if req.model_name else current_cred[2]

    conflict = db.fetch_one(
        "SELECT id FROM llm_credentials WHERE user_id = ? AND provider = ? AND model_name = ? AND id != ?",
        (user_id, target_provider, target_model, cred_id)
    )
    if conflict:
        raise HTTPException(status_code=400, detail=f"修改失败：您已经拥有 [{target_provider}] 的 {target_model} 模型配置。")

    fields = []
    values = []

    if req.provider: fields.append("provider = ?"); values.append(req.provider)
    if req.model_name: fields.append("model_name = ?"); values.append(req.model_name)

    if req.base_url is not None:
        clean_url = req.base_url
        if clean_url and "(" in clean_url and ")" in clean_url:
            try:
                clean_url = clean_url.split("](")[1].split(")")[0]
            except:
                pass
        fields.append("base_url = ?")
        values.append(clean_url)

    if req.api_key:
        fields.append("api_key_enc = ?")
        values.append(encrypt_value(req.api_key))
    if req.secret_key is not None:
        fields.append("secret_key_enc = ?")
        values.append(encrypt_value(req.secret_key) if req.secret_key else None)

    if not fields:
        return {"status": "success", "message": "无变更"}

    values.append(cred_id)
    sql = f"UPDATE llm_credentials SET {', '.join(fields)} WHERE id = ?"

    db.execute(sql, tuple(values))
    return {"status": "success", "message": "配置已更新"}


@router.post("/test-connection")
def test_connection(req: CredentialCreate):
    try:
        clean_url = req.base_url
        if clean_url and "(" in clean_url and ")" in clean_url:
            try:
                clean_url = clean_url.split("](")[1].split(")")[0]
            except:
                pass

        if req.provider == "wenxin":
            llm = WenxinLLM(req.api_key, req.model_name, secret_key=req.secret_key)
        else:
            llm = OpenAILLM(
                api_key=req.api_key,
                model_name=req.model_name,
                base_url=clean_url,
                provider=req.provider
            )

        resp = llm.generate_text("System", "Say 'OK' in 1 word.")
        return {"status": "success", "response": resp}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Connection Failed: {str(e)}")


# --- Endpoints: Preferences (全局偏好) ---

@router.get("/preferences")
def get_preferences(current_user: dict = Depends(get_current_user)):
    user_id = current_user['id']
    row = db.fetch_one("SELECT config_json FROM user_settings WHERE user_id = ?", (user_id,))
    if not row:
        db.execute("INSERT INTO user_settings (user_id) VALUES (?)", (user_id,))
        return {}

    return json.loads(row[0]) if row[0] else {}


@router.put("/preferences")
def update_preferences(req: PreferencesUpdate, current_user: dict = Depends(get_current_user)):
    user_id = current_user['id']

    if not db.fetch_one("SELECT user_id FROM user_settings WHERE user_id = ?", (user_id,)):
        db.execute("INSERT INTO user_settings (user_id) VALUES (?)", (user_id,))

    config_json = req.model_dump_json()
    db.execute("UPDATE user_settings SET config_json = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?", (config_json, user_id))

    return {"status": "success", "message": "偏好设置已同步至云端"}


# --- 🔥 Endpoints: RAG Config (多配置 CRUD) ---

@router.get("/rag-config")
def get_rag_configs(current_user: dict = Depends(get_current_user)):
    user_id = current_user['id']
    rows = db.fetch_all(
        """SELECT id, name, mode, provider, api_key, base_url, online_model_name, local_model_path, is_active 
           FROM rag_config WHERE user_id = ? ORDER BY id DESC""",
        (user_id,)
    )

    # 注意：为了安全，不返回完整的 api_key，只返回掩码 (或者前端不展示)
    # 这里为了编辑方便暂且返回，真实生产环境建议脱敏
    return [
        {
            "id": r[0],
            "name": r[1],
            "mode": r[2],
            "provider": r[3],
            "api_key": r[4],
            "base_url": r[5],
            "online_model_name": r[6],
            "local_model_path": r[7],
            "is_active": bool(r[8])
        }
        for r in rows
    ]


@router.post("/rag-config")
def create_rag_config(req: RagConfigCreate, current_user: dict = Depends(get_current_user)):
    user_id = current_user['id']

    # 插入前先把其他的 active 置为 0 (新添加的默认激活)
    db.execute("UPDATE rag_config SET is_active = 0 WHERE user_id = ?", (user_id,))

    try:
        db.execute(
            """INSERT INTO rag_config 
               (user_id, name, mode, provider, api_key, base_url, online_model_name, local_model_path, is_active, updated_at) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)""",
            (user_id, req.name, req.mode, req.provider, req.api_key, req.base_url, req.online_model_name, req.local_model_path)
        )
        return {"status": "success", "message": "RAG 配置已添加并激活"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/rag-config/{config_id}")
def update_rag_config(config_id: int, req: RagConfigUpdate, current_user: dict = Depends(get_current_user)):
    user_id = current_user['id']

    # 确认存在
    if not db.fetch_one("SELECT id FROM rag_config WHERE id = ? AND user_id = ?", (config_id, user_id)):
        raise HTTPException(status_code=404, detail="配置不存在")

    try:
        db.execute(
            """UPDATE rag_config 
               SET name=?, mode=?, provider=?, api_key=?, base_url=?, online_model_name=?, local_model_path=?, updated_at=CURRENT_TIMESTAMP
               WHERE id = ? AND user_id = ?""",
            (req.name, req.mode, req.provider, req.api_key, req.base_url, req.online_model_name, req.local_model_path, config_id, user_id)
        )
        return {"status": "success", "message": "RAG 配置已更新"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/rag-config/{config_id}")
def delete_rag_config(config_id: int, current_user: dict = Depends(get_current_user)):
    user_id = current_user['id']
    row = db.fetch_one("SELECT is_active FROM rag_config WHERE id = ? AND user_id = ?", (config_id, user_id))
    if not row:
        raise HTTPException(status_code=404, detail="配置不存在")

    was_active = row[0]
    db.execute("DELETE FROM rag_config WHERE id = ?", (config_id,))

    # 如果删除了当前激活的，尝试激活最新的一个
    if was_active:
        latest = db.fetch_one("SELECT id FROM rag_config WHERE user_id = ? ORDER BY id DESC LIMIT 1", (user_id,))
        if latest:
            db.execute("UPDATE rag_config SET is_active = 1 WHERE id = ?", (latest[0],))

    return {"status": "success"}


@router.post("/rag-config/{config_id}/activate")
def activate_rag_config(config_id: int, current_user: dict = Depends(get_current_user)):
    user_id = current_user['id']
    if not db.fetch_one("SELECT id FROM rag_config WHERE id = ? AND user_id = ?", (config_id, user_id)):
        raise HTTPException(status_code=404, detail="配置不存在")

    db.execute("UPDATE rag_config SET is_active = 0 WHERE user_id = ?", (user_id,))
    db.execute("UPDATE rag_config SET is_active = 1 WHERE id = ?", (config_id,))

    return {"status": "success", "message": "已切换 RAG 默认配置"}


@router.post("/rag-config/test")
def test_rag_connection(req: RagConfigCreate):
    """
    测试 RAG 配置是否可用 (尝试 embedding 一段文本)
    """
    try:
        # 使用工厂方法，不读库，直接用 req 参数
        emb_fn = EmbeddingFactory.create_for_test(req.model_dump())

        # 尝试 embed 一个简单的句子
        test_text = "Trinity AI RAG Connection Test"
        embeddings = emb_fn([test_text])

        # 检查输出
        if embeddings and len(embeddings) > 0 and len(embeddings[0]) > 0:
            dim = len(embeddings[0])
            return {"status": "success", "message": f"测试通过！生成维度: {dim}"}
        else:
            raise ValueError("Embedding 生成结果为空")

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Embedding 测试失败: {str(e)}")