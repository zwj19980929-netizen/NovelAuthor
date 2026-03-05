# utils/sse_manager.py
import asyncio
import json
from typing import Dict


class SSEManager:
    """
    管理 Server-Sent Events 的消息队列。
    允许后台同步线程 (Writer) 向前台异步连接 (FastAPI) 推送数据。
    """

    def __init__(self):
        # Key: project_id, Value: asyncio.Queue
        self.connections: Dict[int, asyncio.Queue] = {}
        # 🔥 核心修复：增加一个变量，用来永久保存主线程的事件循环
        self._main_loop = None

    async def connect(self, project_id: int):
        """前端连接时调用（此方法运行在主线程）"""

        # 🔥 核心修复：捕获主线程的 Event Loop
        # 只要有一个用户连接过，我们就能拿到主循环的引用
        if self._main_loop is None:
            try:
                self._main_loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

        if project_id not in self.connections:
            self.connections[project_id] = asyncio.Queue()

        queue = self.connections[project_id]

        # 发送一个连接成功的 ping
        yield self._pack_event("ping", "connected")

        try:
            while True:
                # 等待新消息
                data = await queue.get()
                yield data
                queue.task_done()
        except asyncio.CancelledError:
            # 前端断开连接
            pass

    def send(self, project_id: int, event_type: str, data: dict):
        """
        后台任务调用此方法发送消息。
        此方法可能在子线程中运行，所以必须使用 _main_loop 来调度。
        """
        if project_id in self.connections:
            queue = self.connections[project_id]

            # 🔥 核心修复：使用保存的主循环，而不是尝试在当前线程获取
            if self._main_loop and not self._main_loop.is_closed():
                self._main_loop.call_soon_threadsafe(
                    queue.put_nowait,
                    self._pack_event(event_type, data)
                )
            else:
                # 兜底逻辑：如果实在拿不到 loop（极少见），尝试宽容处理，避免直接 Crash
                try:
                    # 尝试获取全局 loop (但在 worker 线程通常会失败)
                    loop = asyncio.get_event_loop()
                    loop.call_soon_threadsafe(
                        queue.put_nowait,
                        self._pack_event(event_type, data)
                    )
                except Exception:
                    # 如果真的无法发送（比如系统刚启动还没人连SSE），就静默失败，
                    # 不要抛出异常打断生成任务
                    pass

    def _pack_event(self, event_type: str, data: any) -> str:
        """格式化为 SSE 标准格式"""
        payload = json.dumps(data, ensure_ascii=False)
        return f"event: {event_type}\ndata: {payload}\n\n"


# 全局单例
sse_manager = SSEManager()