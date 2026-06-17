"""
会话存储 —— 管理 Agent Loop 的挂起/恢复状态。

当闸门3 触发审批时，Agent Loop 暂停执行。
API 层需要：
1. 保存当前会话状态
2. 返回审批请求给前端
3. 前端提交决策后恢复执行

SessionStore 管理这些生命周期。
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any
from typing import Any, Coroutine


@dataclass
class Session:
    """
    一个进行中的 Agent 会话。

    当 Agent Loop 因审批而挂起时，Session 保存：
    - 恢复所需的协程任务
    - 最终结果的 future
    - 挂起时的内部状态（用于恢复执行）
    """
    session_id: str
    result_future: asyncio.Future
    created_at: float = field(default_factory=lambda: __import__("time").time())
    resume_state: dict[str, Any] | None = None


class SessionStore:
    """
    管理进行中的 Agent 会话。

    用法::

        store = SessionStore()

        # 创建会话
        sid, future = store.create_session()

        # 启动 agent loop 任务（后台运行，结果写入 future）
        asyncio.create_task(run_agent(user_message, future))

        # 等待结果
        result = await future  # 会等待 agent loop 完成（可能经历多次审批）
    """

    # 会话默认超时（秒）
    DEFAULT_TTL = 600

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def create_session(self) -> tuple[str, asyncio.Future]:
        """
        创建一个新会话。

        返回:
            (session_id, result_future)
        """
        sid = str(uuid.uuid4())[:12]
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._sessions[sid] = Session(session_id=sid, result_future=future)
        return sid, future

    def get(self, session_id: str) -> Session | None:
        """根据 ID 获取会话。"""
        return self._sessions.get(session_id)

    def remove(self, session_id: str) -> None:
        """移除已完成/已超时的会话。"""
        self._sessions.pop(session_id, None)

    def cleanup_expired(self, ttl: float | None = None) -> int:
        """清理超时会话，返回清理数量。"""
        import time
        ttl = ttl or self.DEFAULT_TTL
        now = time.time()
        expired = [
            sid for sid, s in self._sessions.items()
            if now - s.created_at > ttl
        ]
        for sid in expired:
            s = self._sessions.pop(sid)
            if not s.result_future.done():
                s.result_future.set_exception(
                    TimeoutError(f"Session {sid} expired")
                )
        return len(expired)
