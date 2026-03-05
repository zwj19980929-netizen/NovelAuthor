# core/planner.py
import json
from utils.llm_provider import LLMFactory
from core.prompts import GLOBAL_ARC_PROMPT, BATCH_PLANNER_PROMPT, ARC_UPDATE_PROMPT
from utils.logger import Logger


class PlannerAgent:
    def __init__(self, project_id: int):
        self.project_id = project_id
        self.logger = Logger(project_id)

        self.llm = LLMFactory.create(project_id=project_id, role="architect")
        self.logger.info(f"规划引擎初始化: 由 [{self.llm.provider}] 负责导航")

    # 🔥 核心修改：增加 total_chapters 参数
    def generate_global_arc(self, world_context: dict, project_name: str, keywords: str, analysis: dict, total_chapters: int = 20) -> str:
        self.logger.ai("正在构建宏观故事弧光 (Global Arc)...")

        world_str = json.dumps(world_context, ensure_ascii=False)

        if not analysis: analysis = {}

        # 🔥 注入 total_chapters
        arc = self.llm.generate_text(
            system_prompt=GLOBAL_ARC_PROMPT.format(
                project_name=project_name,
                keywords=keywords,
                world_context=world_str,
                core_genre=analysis.get('core_genre', '通用'),
                driving_force=analysis.get('driving_force', '剧情'),
                plot_constraints=analysis.get('plot_constraints', '无'),
                total_chapters=total_chapters  # 🔥 传入 Prompt
            ),
            user_prompt="请生成宏观大纲。"
        )
        self.logger.success(f"宏观规划完成: {arc[:50]}...")
        return arc

    def update_global_arc(self, current_chapter: int, old_arc: str, story_summary: str, current_states: dict) -> str:
        self.logger.ai("🔄 正在进行中期复盘 (Mid-term Review)... 校准宏观大纲中...")

        states_str = json.dumps(current_states, ensure_ascii=False)

        sys_prompt = ARC_UPDATE_PROMPT.format(
            current_chapter=current_chapter,
            old_arc=old_arc,
            story_so_far=story_summary,
            world_state=states_str
        )

        new_arc = self.llm.generate_text(
            system_prompt=sys_prompt,
            user_prompt="请更新宏观大纲。"
        )

        self.logger.success(f"✅ 大纲已更新。新方向: {new_arc[:50]}...")
        return new_arc

    # 🔥 核心修改：增加 total_chapters 参数
    def plan_next_batch(self,
                        start_chapter: int,
                        batch_size: int,
                        global_arc: str,
                        recent_summary: str,
                        current_states: dict,
                        project_name: str,
                        keywords: str,
                        style_desc: str,
                        analysis: dict,
                        total_chapters: int = 20,  # 🔥 新增参数
                        human_instruction: str = "") -> list:

        end_chapter = start_chapter + batch_size - 1
        self.logger.ai(f">>> 正在根据标签 [{keywords}] 规划第 {start_chapter} - {end_chapter} 章...")

        states_str = json.dumps(current_states, ensure_ascii=False)

        if not analysis: analysis = {}

        instruction_block = ""
        if human_instruction:
            self.logger.warning(f"⚡ 正在注入上帝指令: {human_instruction}")
            instruction_block = f"""
            \n=========================================================
            🔥 【最高优先级指令 (Human Intervention)】
            总导演刚刚下达了以下剧情指示，你必须无条件执行，并将其融入接下来的剧情规划中：
            指令内容："{human_instruction}"
            =========================================================
            """

        user_input = f"""
        【当前进度】：第 {start_chapter} 章
        【宏观指导 (Global Arc)】：{global_arc}
        【前情摘要】：{recent_summary}
        【当前世界状态】：{states_str}
        {instruction_block}

        请规划接下来的 {batch_size} 章。
        """

        # 🔥 注入 total_chapters
        sys_prompt = BATCH_PLANNER_PROMPT.format(
            project_name=project_name,
            keywords=keywords,
            style_desc=style_desc,
            start_chapter=start_chapter,
            end_chapter=end_chapter,
            global_arc="见下文",
            recent_summary="见下文",
            world_state="见下文",
            batch_size=batch_size,
            core_genre=analysis.get('core_genre', '通用'),
            driving_force=analysis.get('driving_force', '剧情'),
            plot_constraints=analysis.get('plot_constraints', '无'),
            title_aesthetics=analysis.get('title_aesthetics', '常规'),
            total_chapters=total_chapters  # 🔥 传入 Prompt
        )

        data = self.llm.generate_json(
            system_prompt=sys_prompt,
            user_prompt=user_input
        )

        if data and "chapters" in data:
            chapters = data["chapters"]
            self.logger.success(f"规划成功，生成了 {len(chapters)} 章大纲。")
            return chapters

        self.logger.error("规划失败，返回空列表。")
        return []