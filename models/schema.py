# models/schema.py
from typing import List, Dict, Optional, Any, Union
from pydantic import BaseModel, Field, field_validator


# ==================== 1. 世界观与基础 ====================

class WorldPhysics(BaseModel):
    """世界底层物理法则"""
    energy_source: str
    social_hierarchy: str
    impossible_events: str
    currency_logic: str


class CharacterState(BaseModel):
    """角色状态模型"""
    name: str
    # 角色定位
    role: str = Field(description="角色定位，必须是以下之一：'主角', '反派', '配角', '路人'")
    archetype: str
    vector: Dict[str, str] = {}
    resources: List[str] = []

    # 兼容字符串 or 字典输入
    current_status: Union[str, Dict[str, Any]]

    # 兼容字段
    relationships: Dict[str, str] = {}
    inventory: List[str] = []
    status_effects: List[str] = []

    @field_validator('current_status', mode='before')
    @classmethod
    def parse_status(cls, v):
        if isinstance(v, dict):
            return ", ".join([f"{key}: {val}" for key, val in v.items()])
        if isinstance(v, list):
            return ", ".join([str(i) for i in v])
        return v


class CharacterList(BaseModel):
    """用于解析多个角色的容器"""
    characters: List[CharacterState]


# ==================== 2. 文风控制 ====================

class StyleMatrix(BaseModel):
    narrative_voice: str
    sentence_structure: str
    rhetorical_strategy: str
    tone_police: str
    subtext_logic: str


# ==================== 3. 剧情规划 ====================

class GlobalArc(BaseModel):
    hook: str
    journey: str
    climax: str
    resolution: str
    summary: Optional[str] = None


class ChapterOutline(BaseModel):
    title: str
    visual_key: str
    plot_point: str
    # 🔥 新增：微观情节拍子 (Beat Sheet)
    beats: List[str] = []


class BatchPlan(BaseModel):
    chapters: List[ChapterOutline]


# ==================== 4. 审核与更新 ====================

class StoryReview(BaseModel):
    approved: bool
    critique: str


class StateUpdate(BaseModel):
    updates: Dict[str, Dict[str, Any]]