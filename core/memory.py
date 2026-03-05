# core/memory.py
import json
from datetime import datetime
from utils.llm_provider import LLMFactory
from core.prompts import SUMMARY_PROMPT, AUDITOR_PROMPT, LIBRARIAN_PROMPT
from db.manager import db
from utils.logger import Logger


class MemoryManager:
    def __init__(self, project_id: int):
        self.project_id = project_id
        self.db = db
        self.logger = Logger(project_id)
        # 🔥 修改这里：传入 project_id
        self.logician = LLMFactory.create(project_id=project_id, role="logician")

    def get_latest_chapter_num(self) -> int:
        row = self.db.fetch_one("SELECT MAX(chapter_num) FROM chapters WHERE project_id = ?", (self.project_id,))
        return row[0] if row and row[0] else 0

    def get_all_states(self) -> dict:
        latest_chap = self.get_latest_chapter_num()
        sql = """
        SELECT c.name, c.archetype, c.core_vector, 
               s.location, s.current_status, s.inventory, s.relationships
        FROM characters c
        JOIN character_states s ON c.id = s.character_id
        WHERE c.project_id = ? AND s.chapter_num = ?
        """
        rows = self.db.fetch_all(sql, (self.project_id, latest_chap))
        states = {}
        for r in rows:
            name, archetype, vec_json, loc, status, inv_json, rel_json = r
            states[name] = {
                "name": name, "archetype": archetype, "vector": json.loads(vec_json) if vec_json else {},
                "location": loc, "current_status": status,
                "inventory": json.loads(inv_json) if inv_json else [],
                "relationships": json.loads(rel_json) if rel_json else {},
                "status_effects": [status]
            }
        return states

    def retrieve_relevant_memories(self, current_plot: str) -> str:
        self.logger.ai("📚 图书管理员正在检索关联历史...")
        rows = self.db.fetch_all(
            "SELECT chapter_num, title, summary FROM story_summaries WHERE project_id = ? ORDER BY chapter_num ASC",
            (self.project_id,)
        )
        if not rows: return "（暂无历史章节）"
        history_str = "\n".join([f"Ch.{r[0]} [{r[1]}]: {r[2]}" for r in rows])
        try:
            relevant_info = self.logician.generate_text(
                system_prompt=LIBRARIAN_PROMPT,
                user_prompt=f"【新章节大纲】：\n{current_plot}\n\n【历史摘要库】：\n{history_str}"
            )
        except Exception as e:
            self.logger.error(f"检索失败: {e}")
            return "无关联历史"
        return relevant_info

    def _merge_missing_characters(self, current_states_dict: dict, prev_chapter_num: int):
        """
        🔥 核心修复：防止角色丢失。
        检查上一章存在的所有角色，如果这一章的状态列表里没有（可能是AI忘了，也可能是用户刚加的），
        强制把上一章的状态复制过来，确保角色不会“断片”消失。
        """
        if prev_chapter_num < 0: return current_states_dict

        # 查上一章的所有角色状态
        sql = """
        SELECT c.name, c.archetype, c.core_vector, 
               s.location, s.current_status, s.inventory, s.relationships
        FROM characters c
        JOIN character_states s ON c.id = s.character_id
        WHERE c.project_id = ? AND s.chapter_num = ?
        """
        prev_rows = self.db.fetch_all(sql, (self.project_id, prev_chapter_num))

        for r in prev_rows:
            name, archetype, vec_json, loc, status, inv_json, rel_json = r

            # 如果这个角色不在当前的保存列表中，把它补回来
            if name not in current_states_dict:
                # self.logger.info(f"🔄 自动补全遗漏角色: {name}")
                current_states_dict[name] = {
                    "name": name,
                    "archetype": archetype,
                    "vector": json.loads(vec_json) if vec_json else {},
                    "location": loc,
                    "current_status": status,
                    "inventory": json.loads(inv_json) if inv_json else [],
                    "relationships": json.loads(rel_json) if rel_json else {},
                    "status_effects": [status]  # 兼容格式
                }

        return current_states_dict

    def save_chapter(self, chapter_num: int, title: str, content: str, current_states: dict):
        try:
            summary = self.logician.generate_text(system_prompt=SUMMARY_PROMPT, user_prompt=f"章节标题：{title}\n\n正文内容：\n{content}")
        except:
            summary = "（摘要生成失败）"

        # 1. AI 审计更新
        updated_states_dict = self._audit_states(content, current_states)

        # 2. 🔥🔥🔥 核心修复：强制合并上一章的遗漏角色（包括用户刚刚手动添加的）
        # 这样即使 AI 没提到他，或者 memory 变量是旧的，数据库里的最新数据也会被同步过来
        updated_states_dict = self._merge_missing_characters(updated_states_dict, chapter_num - 1)

        try:
            self.db.execute("INSERT INTO chapters (project_id, chapter_num, title, content) VALUES (?, ?, ?, ?)", (self.project_id, chapter_num, title, content))
            self.db.execute("INSERT INTO story_summaries (project_id, chapter_num, title, summary) VALUES (?, ?, ?, ?)", (self.project_id, chapter_num, title, summary))

            for char_name, char_data in updated_states_dict.items():
                char_row = self.db.fetch_one("SELECT id FROM characters WHERE project_id = ? AND name = ?", (self.project_id, char_name))
                if char_row:
                    char_id = char_row[0]
                else:
                    self.logger.success(f"🎉 系统自动收录新角色: {char_name}")
                    char_id = self.db.execute("INSERT INTO characters (project_id, name, archetype, core_vector) VALUES (?, ?, ?, ?)",
                                              (self.project_id, char_name, char_data.get("archetype", "未知"), json.dumps(char_data.get("vector", {}), ensure_ascii=False)))

                # 处理 status 兼容性
                status_val = char_data.get("status_effects", [])
                status_str = str(status_val) if isinstance(status_val, list) else str(char_data.get("current_status", ""))

                self.db.execute(
                    """INSERT INTO character_states (character_id, project_id, chapter_num, location, current_status, inventory, relationships) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (char_id, self.project_id, chapter_num, char_data.get("location", "未知"),
                     status_str,
                     json.dumps(char_data.get("inventory", []), ensure_ascii=False), json.dumps(char_data.get("relationships", {}), ensure_ascii=False))
                )
            self.logger.success(f"记忆归档完成 (Ch.{chapter_num})")
        except Exception as e:
            self.logger.error(f"Save Chapter Error: {e}")
            raise e

    def _audit_states(self, content, old_states):
        self.logger.ai("正在审计角色状态变化...")
        try:
            updates = self.logician.generate_json(system_prompt=AUDITOR_PROMPT, user_prompt=f"【旧状态】：\n{json.dumps(old_states, ensure_ascii=False)}\n\n【本章正文】：\n{content}")
            import copy
            new_states = copy.deepcopy(old_states)
            if updates:
                for name, data in updates.items():
                    if name not in new_states:
                        if "relationships" not in data: data["relationships"] = {}
                        if "vector" not in data: data["vector"] = {}
                        new_states[name] = data
                    else:
                        new_states[name].update(data)
            return new_states
        except Exception as e:
            self.logger.error(f"审计失败: {e}")
            return old_states

    def get_recent_context(self, limit=3):
        rows = self.db.fetch_all("SELECT chapter_num, title, summary FROM story_summaries WHERE project_id = ? ORDER BY chapter_num DESC LIMIT ?", (self.project_id, limit))
        rows.reverse()
        return "\n".join([f"【第{r[0]}章 ({r[1]})】: {r[2]}" for r in rows])