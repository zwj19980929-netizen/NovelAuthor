# core/analyzer.py
import json
from utils.llm_provider import LLMFactory
from core.prompts import STYLE_ANALYSIS_PROMPT
from utils.logger import Logger


class StyleAnalyzer:
    def __init__(self, project_id: int):
        self.project_id = project_id
        self.logger = Logger(project_id)
        self.llm = LLMFactory.create(project_id=project_id, role="architect")

    def analyze(self, project_name: str, keywords: str, style_desc: str) -> dict:
        """
        分析用户输入，生成写作指导书 (Writing Guidelines)
        """
        self.logger.ai(f"🧠 正在深度分析题材基因... [项目: {project_name}]")
        self.logger.ai(f"🔍 关键词: {keywords} | 意向: {style_desc[:20]}...")

        try:
            # 调用 LLM 进行分析
            analysis = self.llm.generate_json(
                system_prompt=STYLE_ANALYSIS_PROMPT.format(
                    project_name=project_name,
                    keywords=keywords,
                    style_desc=style_desc
                ),
                user_prompt="请生成《写作指导书》JSON。"
            )

            if analysis and "core_genre" in analysis:
                self.logger.success(f"💡 风格定位完成: {analysis.get('core_genre')}")
                self.logger.info(f"   - 驱动力: {analysis.get('driving_force')}")
                self.logger.info(f"   - 文风策略: {analysis.get('writing_style')}")
                return analysis

            self.logger.error("❌ 风格分析返回了空数据，使用默认配置。")
            return self._get_default_analysis()

        except Exception as e:
            self.logger.error(f"❌ 风格分析失败: {e}")
            return self._get_default_analysis()

    def _get_default_analysis(self):
        return {
            "core_genre": "通用小说",
            "driving_force": "主角的冒险与成长",
            "narrative_tone": "中立、客观",
            "writing_style": "通顺流畅",
            "plot_constraints": "无特殊限制",
            "title_aesthetics": "常规章节标题"
        }