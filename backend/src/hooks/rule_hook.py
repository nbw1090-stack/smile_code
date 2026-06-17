"""
闸门2 + 闸门3 钩子 —— RuleEngineHook

在 before_tool_execution 阶段执行（priority=20，闸门1之后）。
命中上下文规则 → 返回 NEEDS_APPROVAL，暂停等待用户决策。

内置闸门3审批管理（asyncio.Event 机制）。
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from src.hooks.base import BaseHook, HookAction, HookContext, HookPoint, HookResult
from src.security.rule_engine import RuleEngine, RuleMatch
from src.security.workspace import Workspace


@dataclass
class _ApprovalContext:
    """审批上下文（内部使用）。"""
    request_id: str
    tool_name: str
    tool_input: dict[str, Any]
    rule_matches: list[RuleMatch]
    event: asyncio.Event
    approved: bool | None = None


class RuleEngineHook(BaseHook):
    """
    闸门2 + 闸门3 —— 规则引擎 + 审批管理钩子。

    优先级 20（在 DenyListHook 之后执行）。
    命中规则后创建审批请求，通过 asyncio.Event 暂停等待。
    """

    DEFAULT_TIMEOUT = 300  # 审批超时秒数

    def __init__(
        self,
        rule_engine: RuleEngine | None = None,
        workspace: Workspace | None = None,
    ) -> None:
        self._rule_engine = rule_engine or RuleEngine()
        self._workspace = workspace or Workspace()
        self._pending: dict[str, _ApprovalContext] = {}

    @property
    def name(self) -> str:
        return "rule_engine"

    @property
    def hook_point(self) -> HookPoint:
        return HookPoint.BEFORE_TOOL_EXECUTION

    @property
    def priority(self) -> int:
        return 20  # 在 deny_list 之后

    async def execute(self, context: HookContext) -> HookResult:
        rule_matches = self._rule_engine.check(
            context.tool_name, context.tool_input, self._workspace
        )
        if not rule_matches:
            return HookResult(action=HookAction.CONTINUE)

        # 命中规则 → 创建审批请求
        request_id = str(uuid.uuid4())[:8]
        ctx = _ApprovalContext(
            request_id=request_id,
            tool_name=context.tool_name,
            tool_input=context.tool_input,
            rule_matches=rule_matches,
            event=asyncio.Event(),
        )
        self._pending[request_id] = ctx

        reasons = [m.description for m in rule_matches]
        return HookResult(
            action=HookAction.NEEDS_APPROVAL,
            message="; ".join(reasons),
            data={
                "request_id": request_id,
                "tool_name": context.tool_name,
                "tool_input": context.tool_input,
                "rules": [
                    {
                        "rule_name": m.rule_name,
                        "severity": m.severity,
                        "description": m.description,
                        "detail": m.detail,
                    }
                    for m in rule_matches
                ],
            },
        )

    # ------------------------------------------------------------------
    # 闸门3 审批操作
    # ------------------------------------------------------------------

    def get_pending_request(self, request_id: str) -> dict[str, Any] | None:
        """获取待审批请求详情。"""
        ctx = self._pending.get(request_id)
        if ctx is None:
            return None
        return {
            "request_id": ctx.request_id,
            "tool_name": ctx.tool_name,
            "tool_params": ctx.tool_input,
            "rules": [
                {
                    "rule_name": m.rule_name,
                    "severity": m.severity,
                    "description": m.description,
                    "detail": m.detail,
                }
                for m in ctx.rule_matches
            ],
        }

    def approve(self, request_id: str, approved: bool) -> bool:
        """提交审批决策。"""
        ctx = self._pending.get(request_id)
        if ctx is None:
            return False
        ctx.approved = approved
        ctx.event.set()
        return True

    async def wait_for_approval(
        self, request_id: str, timeout: float | None = None
    ) -> bool:
        """等待审批决策（异步阻塞），返回是否批准。"""
        timeout = timeout or self.DEFAULT_TIMEOUT
        ctx = self._pending.get(request_id)
        if ctx is None:
            return False

        try:
            await asyncio.wait_for(ctx.event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            ctx.approved = False

        approved = ctx.approved or False
        self._pending.pop(request_id, None)
        return approved

    def list_pending_requests(self) -> list[str]:
        """列出所有待审批请求 ID。"""
        return list(self._pending.keys())
