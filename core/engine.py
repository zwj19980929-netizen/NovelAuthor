# core/engine.py
import json
import time
from datetime import datetime
from db.manager import db
from utils.llm_provider import LLMFactory
from core.planner import PlannerAgent
from core.stylist import StylistAgent
from core.writer import StoryWriter
from core.memory import MemoryManager
from core.prompts import ONTOLOGY_PROMPT, CHARACTER_PROMPT
from models.schema import WorldPhysics, CharacterState, CharacterList
from utils.logger import Logger
from core.analyzer import StyleAnalyzer


class TrinityEngine:
    def __init__(self):
        self.db = db

    def async_build_world(self, project_id, keywords, style_desc):
        logger = Logger(project_id)
        try:
            # 🔥 获取项目名和 total_chapters
            proj_row = self.db.fetch_one("SELECT name, total_chapters FROM projects WHERE id = ?", (project_id,))
            project_name = proj_row[0] if proj_row else "未命名"
            total_chapters = proj_row[1] if proj_row and proj_row[1] else 20

            logger.ai("正在加载世界架构模块...")
            llm = LLMFactory.create(project_id=project_id, role="ontology")

            # Step 0: 风格分析
            analyzer = StyleAnalyzer(project_id)
            analysis = analyzer.analyze(project_name, keywords, style_desc)

            # Step 1: 确立文风矩阵
            stylist = StylistAgent(project_id)
            style_matrix = stylist.generate_style_matrix(analysis)

            planner = PlannerAgent(project_id)

            logger.ai("Step 2/4: 构建世界本体论 (Ontology)...")
            world_physics = llm.generate_json(
                system_prompt=ONTOLOGY_PROMPT,
                user_prompt=f"关键词：{keywords}",
                pydantic_model=WorldPhysics
            )

            if isinstance(world_physics, dict):
                logger.error("世界观生成失败 (JSON解析错误)，尝试使用兜底配置...")
                world_physics = WorldPhysics(
                    energy_source="未知",
                    social_hierarchy="未知",
                    impossible_events="无",
                    currency_logic="金钱"
                )

            logger.success("世界底层物理法则已确立。")

            logger.ai("Step 3/4: 选角与人物建模 (Casting)...")

            # 🔥🔥🔥 核心修复：这里把 project_name 传进去，并强制要求 AI 检查标题
            # 以前这里只传了 physics，导致 AI 瞎编名字
            character_user_prompt = f"""
            小说标题：《{project_name}》
            关键词：{keywords}
            世界规则：{world_physics.model_dump_json()}

            请生成一组核心角色。
            ⚠️ 重要指令：如果【小说标题】中包含明显的人名（例如《再见陈平安》中的“陈平安”，或《哈利波特》），请务必将该人名作为【主角】创建！
            绝对不要生成“林逸”、“叶凡”这种通用名字，除非标题里没写名字。
            """

            char_data_obj = llm.generate_json(
                system_prompt=CHARACTER_PROMPT,
                user_prompt=character_user_prompt,
                pydantic_model=CharacterList
            )

            if isinstance(char_data_obj, dict):
                logger.error("角色生成失败，跳过选角步骤。")
                chars_list = []
            else:
                chars_list = char_data_obj.characters

            for char in chars_list:
                try:
                    char_role = char.role if hasattr(char, 'role') and char.role else "配角"
                    char_id = self.db.execute(
                        "INSERT INTO characters (project_id, name, archetype, core_vector, role) VALUES (?, ?, ?, ?, ?)",
                        (project_id, char.name, char.archetype, json.dumps(char.vector, ensure_ascii=False), char_role)
                    )

                    status_val = char.current_status
                    if not isinstance(status_val, str):
                        status_str = json.dumps(status_val, ensure_ascii=False)
                    else:
                        status_str = status_val

                    self.db.execute(
                        """INSERT INTO character_states 
                           (character_id, project_id, chapter_num, location, current_status, inventory, relationships)
                           VALUES (?, ?, 0, ?, ?, ?, ?)""",
                        (char_id, project_id, "初始位置", status_str, json.dumps(char.resources, ensure_ascii=False), json.dumps(char.relationships, ensure_ascii=False))
                    )
                except Exception as e:
                    print(f"Character Insert Error: {e}")
                    pass

            world_config = {
                "physics": world_physics.model_dump(),
                "style_matrix": style_matrix,
                "style_analysis": analysis
            }

            logger.ai("Step 4/4: 规划宏观故事弧光 (Global Arc)...")

            chars_dump = [c.model_dump() for c in chars_list]
            temp_context = {"physics": world_physics.model_dump(), "characters": chars_dump}

            # 🔥 传递 total_chapters 给规划师
            global_arc_text = planner.generate_global_arc(temp_context, project_name, keywords, analysis, total_chapters)

            if not global_arc_text:
                global_arc_text = "（大纲生成失败，请在正文中自行探索）"

            self.db.execute(
                """INSERT INTO global_arcs (project_id, hook, journey, climax, resolution, full_analysis, version, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, 1, 1)""",
                (project_id, "详见正文", global_arc_text, "详见正文", "详见正文", "")
            )

            self.db.execute("UPDATE projects SET world_config = ? WHERE id = ?", (json.dumps(world_config, ensure_ascii=False), project_id))
            logger.success("✅ 项目初始化彻底完成！")

        except Exception as e:
            logger.error(f"❌ 初始化过程发生严重错误: {e}")
            import traceback
            traceback.print_exc()

    def rollback_story(self, project_id: int, target_chapter_num: int):
        logger = Logger(project_id)
        logger.warning(f"正在执行时光倒流... 目标回滚至第 {target_chapter_num} 章之前")
        try:
            self.db.execute("DELETE FROM chapters WHERE project_id = ? AND chapter_num >= ?", (project_id, target_chapter_num))
            self.db.execute("DELETE FROM story_summaries WHERE project_id = ? AND chapter_num >= ?", (project_id, target_chapter_num))
            self.db.execute("DELETE FROM character_states WHERE project_id = ? AND chapter_num >= ?", (project_id, target_chapter_num))
            self.db.execute("DELETE FROM chapter_outlines WHERE project_id = ? AND chapter_num >= ?", (project_id, target_chapter_num))
            logger.success(f"⏪ 回滚成功！")
        except Exception as e:
            logger.error(f"❌ 回滚失败: {e}")
            raise e

    def run_batch(self, project_id: int, human_instruction: str = ""):
        logger = Logger(project_id)
        # 🔥 获取 total_chapters
        row = self.db.fetch_one("SELECT keywords, style_desc, world_config, name, total_chapters FROM projects WHERE id = ?", (project_id,))
        if not row: return
        keywords, style_desc, world_config_json, project_name, total_chapters = row
        if not total_chapters: total_chapters = 20

        world_config = json.loads(world_config_json) if world_config_json else {}

        style_matrix = world_config.get("style_matrix")
        analysis = world_config.get("style_analysis")

        if not analysis:
            analyzer = StyleAnalyzer(project_id)
            analysis = analyzer.analyze(project_name, keywords, style_desc)
            world_config['style_analysis'] = analysis
            self.db.execute("UPDATE projects SET world_config = ? WHERE id = ?", (json.dumps(world_config, ensure_ascii=False), project_id))

        stylist = StylistAgent(project_id)
        planner = PlannerAgent(project_id)
        writer = StoryWriter(project_id)
        memory = MemoryManager(project_id)

        if not style_matrix:
            style_matrix = stylist.generate_style_matrix(analysis)
            if world_config:
                world_config['style_matrix'] = style_matrix
                self.db.execute("UPDATE projects SET world_config = ? WHERE id = ?", (json.dumps(world_config, ensure_ascii=False), project_id))

        arc_row = self.db.fetch_one("SELECT hook, journey, climax, resolution FROM global_arcs WHERE project_id = ? AND is_active = 1 ORDER BY id DESC LIMIT 1", (project_id,))

        if not arc_row:
            logger.warning("⚠️ 检测到宏观大纲缺失 (可能因上次初始化失败)。正在尝试紧急修复...")

            physics = world_config.get('physics', {"energy_source": "未知", "social_hierarchy": "未知"})
            chars_rows = self.db.fetch_all("SELECT name, archetype, core_vector FROM characters WHERE project_id = ?", (project_id,))
            chars_data = [{"name": r[0], "archetype": r[1], "vector": json.loads(r[2]) if r[2] else {}} for r in chars_rows]

            temp_context = {"physics": physics, "characters": chars_data}

            try:
                # 🔥 补全调用
                new_arc_text = planner.generate_global_arc(temp_context, project_name, keywords, analysis, total_chapters)
                self.db.execute(
                    """INSERT INTO global_arcs (project_id, hook, journey, climax, resolution, full_analysis, version, is_active)
                       VALUES (?, ?, ?, ?, ?, ?, 1, 1)""",
                    (project_id, "自动生成起因", new_arc_text, "自动生成高潮", "自动生成结局", "")
                )
                global_arc_text = new_arc_text
                logger.success("✅ 宏观大纲已自动补全。")
            except Exception as e:
                logger.error(f"❌ 无法生成宏观大纲，请尝试新建项目。错误: {e}")
                return
        else:
            global_arc_text = f"{arc_row[0]}\n{arc_row[1]}\n{arc_row[2]}\n{arc_row[3]}"

        BATCH_SIZE = 3
        current_chapter_num = memory.get_latest_chapter_num()
        next_chapter_num = current_chapter_num + 1

        logger.info(f"🚀 [批量模式] 准备生成第 {next_chapter_num} - {next_chapter_num + BATCH_SIZE - 1} 章...")

        current_states = memory.get_all_states()
        writer_context = {"physics": world_config.get("physics", {}), "characters": list(current_states.values())}
        recent_summary = memory.get_recent_context(limit=5)

        # 🔥 传递 total_chapters
        outlines = planner.plan_next_batch(
            start_chapter=next_chapter_num,
            batch_size=BATCH_SIZE,
            global_arc=global_arc_text,
            recent_summary=recent_summary,
            current_states=current_states,
            project_name=project_name,
            keywords=keywords,
            style_desc=style_desc,
            analysis=analysis,
            total_chapters=total_chapters,  # 🔥
            human_instruction=human_instruction
        )

        if not outlines:
            logger.error("❌ 大纲规划失败，AI 返回了空数据。")
            return

        for outline in outlines:
            if isinstance(outline, dict):
                title = outline.get('title', '无题')
                visual = outline.get('visual_key', '无')
                plot = outline.get('plot_point', '无')
                beats = outline.get('beats', [])
            else:
                title = outline.title
                visual = outline.visual_key
                plot = outline.plot_point
                beats = outline.beats

            chap_idx = outlines.index(outline)
            real_chap_num = next_chapter_num + chap_idx

            self.db.execute(
                """INSERT OR REPLACE INTO chapter_outlines (project_id, chapter_num, title, visual_key, plot_point)
                   VALUES (?, ?, ?, ?, ?)""",
                (project_id, real_chap_num, title, visual, plot)
            )

        outline_obj_list = []
        for o in outlines:
            if hasattr(o, 'dict'):
                outline_obj_list.append(o.dict())
            elif isinstance(o, dict):
                outline_obj_list.append(o)

        outline_str = json.dumps({"chapters": outline_obj_list}, ensure_ascii=False)
        writer.write_batch(writer_context, outline_str, style_matrix, analysis)
        logger.success(f"✨ 批次任务完成！")