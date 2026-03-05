# core/stylist.py
import json
from utils.llm_provider import LLMFactory
from core.prompts import STYLIST_PROMPT
from utils.logger import Logger


class StylistAgent:
    def __init__(self, project_id: int):
        self.project_id = project_id
        self.logger = Logger(project_id)
        self.llm = LLMFactory.create(project_id=project_id, role="architect")
        self.logger.info(f"文学顾问已就位: 由 [{self.llm.provider}] 负责文风立法")

    def generate_style_matrix(self, style_guide_json: dict) -> dict:
        """
        根据《写作指导书》，生成结构化的文风矩阵
        """
        # 将指导书字典转为字符串描述，传给 LLM
        guide_str = json.dumps(style_guide_json, ensure_ascii=False)

        self.logger.ai(f"正在根据指导书制定执行矩阵...")

        try:
            matrix = self.llm.generate_json(
                system_prompt=STYLIST_PROMPT.format(style_guide=guide_str),
                user_prompt="请生成文风矩阵 JSON。"
            )

            if matrix and "tone_police" in matrix:
                self.logger.success(f"文风矩阵已确立: {matrix.get('narrative_voice', '未知')[:30]}...")
                return matrix
            else:
                raise ValueError("生成的 JSON 结构缺失关键字段")

        except Exception as e:
            self.logger.error(f"文风解析失败，使用默认风格: {e}")
            return {
                "narrative_voice": "冷静的第三人称",
                "sentence_structure": "标准书面语",
                "rhetorical_strategy": "注重视觉描写",
                "tone_police": "避免流水账",
                "subtext_logic": "通过动作表现心理"
            }