from utils.llm_provider import LLMFactory
from core.prompts import ARCHITECT_PROMPT, LOGICIAN_PROMPT
from colorama import Fore, Style


class DebateEngine:
    # 🔥 Fix: 增加 project_id 参数
    def __init__(self, project_id: int):
        # 告诉工厂：我要一个创意师，我要一个逻辑官。
        # 🔥 Fix: 将 project_id 传给工厂，否则报错
        self.architect_llm = LLMFactory.create(project_id=project_id, role="architect")
        self.logician_llm = LLMFactory.create(project_id=project_id, role="logician")

        print(f"{Fore.YELLOW}辩论引擎初始化完毕:")
        print(f"  - 创意师由 [{self.architect_llm.provider}] 扮演")
        print(f"  - 逻辑官由 [{self.logician_llm.provider}] 扮演{Fore.RESET}")

    def run_debate(self, context: str, rounds: int = 2) -> str:
        # 代码无需更改，保持原样
        print(f"\n{Fore.CYAN}=== 开启多智能体审议 (Multi-Agent Deliberation) ==={Style.RESET_ALL}")

        proposal = self.architect_llm.generate_text(
            system_prompt=ARCHITECT_PROMPT,
            user_prompt=f"背景设定：{context}\n\n请生成一段剧情大纲，包含起承转合。"
        )
        print(f"{Fore.GREEN}[创意师]: {proposal[:100]}...{Style.RESET_ALL}")

        for i in range(rounds):
            critique = self.logician_llm.generate_text(
                system_prompt=LOGICIAN_PROMPT,
                user_prompt=f"提案内容：{proposal}\n\n请找出逻辑漏洞。"
            )
            print(f"{Fore.RED}[逻辑官]: {critique}{Style.RESET_ALL}")

            proposal = self.architect_llm.generate_text(
                system_prompt=ARCHITECT_PROMPT,
                user_prompt=f"原提案：{proposal}\n逻辑漏洞：{critique}\n\n请修正提案，保留戏剧性但修复逻辑。"
            )
            print(f"{Fore.GREEN}[创意师 (修正版 v{i + 1})]: {proposal[:100]}...{Style.RESET_ALL}")

        return proposal