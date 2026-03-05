# core/writer.py
import json
from utils.llm_provider import LLMFactory
from core.prompts import WRITER_PROMPT_V2, CHAPTER_PARSER_PROMPT, POLISH_PASS_PROMPT
from core.memory import MemoryManager
from core.critic import CriticAgent
from core.rag import RAGManager, StyleRAGManager  # 🔥 引入 StyleRAGManager
from utils.logger import Logger
from db.manager import db
from utils.sse_manager import sse_manager


class StoryWriter:

    def __init__(self, project_id: int):
        self.project_id = project_id
        self.logger = Logger(project_id)
        self.db = db

        user_row = self.db.fetch_one("SELECT user_id FROM projects WHERE id = ?", (project_id,))
        if user_row:
            self.user_id = user_row[0]
        else:
            self.user_id = 1
            self.logger.warning("⚠️ 未找到项目所属用户，默认使用 ID=1")

        self.llm = LLMFactory.create(project_id=project_id, role="writer")
        self.critic = CriticAgent(project_id)
        self.rag = RAGManager(project_id=project_id, user_id=self.user_id)
        # 🔥 初始化样式检索器
        self.style_rag = StyleRAGManager(user_id=self.user_id)

    def _parse_outline_to_chapters(self, outline_text: str, analysis: dict):
        try:
            data = json.loads(outline_text)
            if "chapters" in data: return data["chapters"]
        except:
            pass

        self.logger.info("正在结构化大纲...")
        struct_llm = LLMFactory.create(project_id=self.project_id, role="architect")

        title_aes = analysis.get('title_aesthetics', '常规') if analysis else '常规'

        data = struct_llm.generate_json(
            system_prompt=CHAPTER_PARSER_PROMPT.format(title_aesthetics=title_aes),
            user_prompt=f"请将以下大纲转化为章节列表 JSON：\n\n{outline_text}"
        )
        if data and "chapters" in data: return data["chapters"]
        return []

    def _format_character_context(self, current_states: dict) -> str:
        main_chars = []
        villains = []
        supports = []
        others = []

        for name, data in current_states.items():
            row = self.db.fetch_one("SELECT role FROM characters WHERE project_id = ? AND name = ?", (self.project_id, name))
            role = row[0] if row else "配角"

            info = f"姓名：{name} | 状态：{data.get('current_status', '未知')}"

            if role == "主角":
                vec = data.get("vector", {})
                info += f"\n   - 核心欲望: {vec.get('target', '未知')}"
                info += f"\n   - 致命恐惧: {vec.get('fear', '未知')}"
                main_chars.append(info)
            elif role == "反派":
                vec = data.get("vector", {})
                info += f"\n   - 对抗目标: {vec.get('target', '未知')}"
                villains.append(info)
            elif role == "配角":
                supports.append(info)
            else:
                others.append(name)

        context_str = "【核心聚焦 (Protagonists)】\n" + "\n".join(main_chars) + "\n\n"
        if villains:
            context_str += "【对抗势力 (Antagonists)】\n" + "\n".join(villains) + "\n\n"
        if supports:
            context_str += "【辅助角色 (Supporting)】\n" + "\n".join(supports) + "\n\n"

        return context_str

    def write_batch(self, world_context: dict, outline_text: str, style_matrix: dict, analysis: dict) -> list:
        memory = MemoryManager(self.project_id)

        # 1. 获取项目配置
        row = self.db.fetch_one("SELECT target_word_count, name, keywords, style_ref_id, author_preset_id FROM projects WHERE id = ?", (self.project_id,))
        if not row: return []

        target_count, project_name, project_keywords, style_ref_id, author_preset_id = row
        if not target_count: target_count = 2000

        chapters = self._parse_outline_to_chapters(outline_text, analysis)
        if not chapters: return []

        if not analysis: analysis = {}

        generated_chapters = []

        for index, chapter in enumerate(chapters):
            chapter_num = chapter.get('chapter_num', memory.get_latest_chapter_num() + 1)
            chapter['chapter_num'] = chapter_num

            title = chapter.get('title', f"第 {chapter_num} 章")
            visual = chapter.get('visual_key', '无')
            plot = chapter.get('plot_point', '无')
            beats = chapter.get('beats', [])
            beats_str = "\n".join(beats) if beats else "(本章未规划详细拍子，请根据剧情梗概自由发挥)"

            self.logger.info(f"🚀 正在策划: 第 {chapter_num} 章 - {title}")

            # ==================== 🔥 智能样章检索 ====================
            style_ref_block = ""

            if author_preset_id:
                # 构造查询语句：结合画面感和剧情，去作者库里找类似的描写
                search_query = f"{visual} {plot} {beats_str[:100]}"
                self.logger.ai(f"🔍 正在作者库中检索最匹配的写法... (Query: {visual[:20]}...)")

                # 检索 Top 1 (最相关的)
                found_sample = self.style_rag.search_relevant_style(author_preset_id, search_query, n_results=1)

                if found_sample:
                    style_ref_block = found_sample
                    # 提取标题用于日志展示
                    try:
                        sample_title = found_sample.split('【参考范例：')[1].split('】')[0]
                        self.logger.success(f"💡 灵感匹配：发现类似写法《{sample_title}》")
                    except:
                        self.logger.success(f"💡 灵感匹配：发现一段高相关性的例章。")
                else:
                    self.logger.info("ℹ️ 未在作者库中找到相关例章，将根据风格画像自由发挥。")
                    style_ref_block = "（未匹配到特定例章，请严格遵守风格画像）"

            elif style_ref_id:
                # 旧逻辑：固定样章
                row_style = self.db.fetch_one("SELECT content, name FROM style_references WHERE id = ?", (style_ref_id,))
                if row_style:
                    style_ref_block = f"【指定样章参考：{row_style[1]}】\n{row_style[0][:3000]}"
            else:
                style_ref_block = "（无样章）"
            # ========================================================

            recent_context = memory.get_recent_context(limit=3) or "故事刚刚开始。"

            # RAG 剧情回顾
            search_query_plot = f"{plot} {visual} {title}"
            rag_memory = "（数据库暂空）"
            try:
                if self.rag.count() > 0:
                    rag_memory = self.rag.search(search_query_plot, n_results=3)
            except Exception as e:
                self.logger.warning(f"RAG 剧情检索暂不可用: {e}")

            current_states = memory.get_all_states()
            if not current_states:
                chars = world_context.get('characters', [])
                current_states = {c['name']: c for c in chars}

            formatted_char_context = self._format_character_context(current_states)

            # 3. 构造基础 Prompt
            sys_prompt_base = WRITER_PROMPT_V2.format(
                project_name=project_name,
                keywords=project_keywords,
                title=title,
                visual=visual,
                plot=plot,
                beats_str=beats_str,
                style_ref_block=style_ref_block,  # 🔥 这里传入的是检索到的最佳例章
                rag_memory=rag_memory,
                narrative_voice=style_matrix.get('narrative_voice', '中立'),
                tone_police=style_matrix.get('tone_police', '无'),
                world_context=f"""
                【世界观规则】：{json.dumps(world_context.get('physics', {}), ensure_ascii=False)}

                {formatted_char_context} 
                【前情提要】：{recent_context}
                """,
                core_genre=analysis.get('core_genre', '通用'),
                narrative_tone=analysis.get('narrative_tone', '标准'),
                writing_style=analysis.get('writing_style', '通顺'),
                plot_constraints=analysis.get('plot_constraints', '无')
            )

            max_retries = 2
            current_draft = ""
            feedback = ""

            sse_manager.send(self.project_id, "stream_start", {"chapter_num": chapter_num, "title": title})

            for attempt in range(max_retries):
                current_draft = ""

                # 第一段生成
                self.logger.ai(f"正在生成第 {attempt + 1} 稿 (Part 1)...")
                len_instruction = f"\n⚠️ 字数要求：本章目标是 {target_count} 字。请先写完本章的前半部分。"
                prompt_suffix = f"\n\n❌【前次修改意见】：\n{feedback}\n\n请重写。" if feedback else ""

                user_prompt = f"请开始撰写正文：{len_instruction}" + prompt_suffix

                try:
                    for chunk in self.llm.stream_text(sys_prompt_base, user_prompt):
                        current_draft += chunk
                        sse_manager.send(self.project_id, "stream_chunk", {"chunk": chunk})
                except Exception as e:
                    self.logger.error(f"Part 1 生成中断: {e}")

                # 自动续写
                expansion_count = 0
                max_expansions = 5

                while len(current_draft) < target_count * 0.9 and expansion_count < max_expansions:
                    expansion_count += 1
                    missing_words = target_count - len(current_draft)
                    self.logger.ai(f"📝 字数不足 ({len(current_draft)}/{target_count})，正在进行第 {expansion_count} 次续写...")

                    last_context = current_draft[-1000:]

                    continue_prompt = f"""
                    你正在写这一章，目前字数不足，需要继续扩写。

                    【本章核心拍子(Beats)】：
                    {beats_str}

                    【前文回顾】：
                    ...{last_context}

                    【续写指令】：
                    1. **无缝衔接**：请紧接【前文回顾】的最后一个字，继续向下撰写。
                    2. **禁止重复**：绝对不要重复【前文回顾】里的内容！
                    3. **禁止废话**：不要输出“好的”、“接下文”等提示语，直接输出正文。
                    4. **目标**：还需要补充约 {missing_words} 字。
                    """

                    try:
                        for chunk in self.llm.stream_text(sys_prompt_base, continue_prompt):
                            current_draft += chunk
                            sse_manager.send(self.project_id, "stream_chunk", {"chunk": chunk})
                    except Exception as e:
                        self.logger.error(f"续写中断: {e}")
                        break

                current_len = len(current_draft)
                min_len = target_count * 0.8

                if current_len < min_len:
                    feedback = f"字数严重不足（当前 {current_len} 字），目标是 {target_count} 字。"
                    self.logger.warning(f"❌ 即使续写后字数仍不足: {feedback} -> 尝试重写")
                    continue

                review_result = self.critic.review_chapter(chapter, current_draft, style_matrix, analysis)
                if review_result['approved']:
                    self.logger.success(f"✅ 总编剧通过 (字数: {current_len})。")
                    break
                else:
                    feedback = review_result['critique']
                    self.logger.warning(f"❌ 剧情审核未通过: {feedback} -> 正在重写")

            # 润色
            self.logger.ai("✨ 正在进行文学润色 (Polishing Pass)...")
            polish_prompt = POLISH_PASS_PROMPT.format(
                writing_style=analysis.get('writing_style', '通顺'),
                draft=current_draft
            )

            try:
                polished_draft = self.llm.generate_text(
                    system_prompt="你是一个资深文学编辑。",
                    user_prompt=polish_prompt
                )
                if len(polished_draft) > len(current_draft) * 0.7:
                    current_draft = polished_draft
                    self.logger.success("✨ 润色完成，文笔质感已提升。")
                else:
                    self.logger.warning("⚠️ 润色后字数损失过多，保留初稿。")
            except Exception as e:
                self.logger.error(f"润色失败: {e}")

            sse_manager.send(self.project_id, "stream_end", {"full_text": current_draft})

            # 保存
            memory.save_chapter(chapter_num, title, current_draft, current_states)

            # RAG 索引
            if current_draft and len(current_draft) > 100:
                try:
                    self.rag.add_chapter(chapter_num, title, current_draft)
                except Exception as e:
                    self.logger.warning(f"RAG 索引失败: {e}")

            generated_chapters.append({
                "chapter_num": chapter_num,
                "title": title,
                "content": current_draft
            })

        return generated_chapters