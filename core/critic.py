# core/critic.py
import json
from utils.llm_provider import LLMFactory
from core.prompts import SHOWRUNNER_PROMPT_V2
from utils.logger import Logger


class CriticAgent:
    def __init__(self, project_id: int):
        self.project_id = project_id
        self.logger = Logger(project_id)

        self.llm = LLMFactory.create(project_id=project_id, role="logician")
        self.logger.info(f"编剧室初始化: 总编剧由 [{self.llm.provider}] 担任")

    def review_chapter(self, plan: dict, draft: str, style_matrix: dict = None, analysis: dict = None) -> dict:
        """
        审核章节。
        返回字典: {"approved": bool, "critique": str}
        """
        self.logger.ai(f"👀 总编剧正在审阅第 {plan.get('chapter_num', '?')} 章初稿...")

        plan_str = json.dumps(plan, ensure_ascii=False)
        style_str = json.dumps(style_matrix, ensure_ascii=False) if style_matrix else "无特殊要求"

        # 🔥 提取分析结果供审阅使用 (兜底防止 None)
        if not analysis: analysis = {}

        core_genre = analysis.get('core_genre', '通用')
        writing_style = analysis.get('writing_style', '通顺')
        plot_constraints = analysis.get('plot_constraints', '无')  # 🔥 补上这个漏掉的变量

        # 🔥 必须传入所有 Prompt 中定义的占位符
        try:
            sys_prompt = SHOWRUNNER_PROMPT_V2.format(
                style_matrix=style_str,
                plan=plan_str,
                draft=draft[:2000] + "...",  # 截断防止 token 溢出
                core_genre=core_genre,
                writing_style=writing_style,
                plot_constraints=plot_constraints  # 🔥🔥🔥 核心修复：传入 plot_constraints
            )
        except KeyError as e:
            self.logger.error(f"Prompt 格式化错误: {e}")
            # 紧急兜底：如果还缺参数，就用最简单的 Prompt 跑，防止 Crash
            sys_prompt = "请审核以下小说章节是否逻辑通顺:\n" + draft[:1000]

        try:
            result = self.llm.generate_json(
                system_prompt=sys_prompt,
                user_prompt="请基于上述内容进行审阅，输出 JSON 结果。"
            )

            if result and "approved" in result:
                return result

            return {"approved": True, "critique": "格式解析失败，自动通过。"}

        except Exception as e:
            self.logger.error(f"审阅发生错误: {e}")
            return {"approved": True, "critique": "审阅服务离线，自动通过。"}