# utils/logger.py
import re
from datetime import datetime
from colorama import Fore, Style
from db.manager import db
from utils.sse_manager import sse_manager # 🔥 引入 SSE 管理器

class Logger:
    def __init__(self, project_id=None):
        self.db = db
        self.project_id = project_id

    def _strip_ansi(self, text):
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)

    def log(self, message: str, color=Fore.WHITE, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"{Fore.CYAN}[{timestamp}]{Style.RESET_ALL} {color}{message}{Style.RESET_ALL}")

        clean_msg = self._strip_ansi(message)
        try:
            if self.project_id:
                # 1. 存库
                self.db.execute(
                    "INSERT INTO system_logs (project_id, level, message, timestamp) VALUES (?, ?, ?, ?)",
                    (self.project_id, level, clean_msg, datetime.now())
                )
                # 2. 🔥 推送 SSE 事件
                sse_manager.send(self.project_id, "log", {
                    "time": timestamp,
                    "level": level,
                    "msg": clean_msg
                })
        except Exception as e:
            print(f"{Fore.RED}❌ [Logger Error]: {e}{Fore.RESET}")

    def info(self, msg): self.log(msg, Fore.WHITE, "INFO")
    def success(self, msg): self.log(msg, Fore.GREEN, "SUCCESS")
    def warning(self, msg): self.log(msg, Fore.YELLOW, "WARNING")
    def error(self, msg): self.log(msg, Fore.RED, "ERROR")
    def ai(self, msg): self.log(msg, Fore.CYAN, "AI_THOUGHT")