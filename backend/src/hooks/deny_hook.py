"""
闸门1 钩子 —— DenyListHook

在 before_tool_execution 阶段执行（priority=10，最先执行）。
命中拒绝列表 → 返回 ABORT，工具不执行。
"""

from src.hooks.base import BaseHook, HookAction, HookContext, HookPoint, HookResult
from src.security.deny_list import DenyList


class DenyListHook(BaseHook):
    """
    闸门1 —— 拒绝列表钩子。

    优先级最高（10），在工具执行前检查是否命中拒绝列表。
    """

    def __init__(self, deny_list: DenyList | None = None) -> None:
        self._deny_list = deny_list or DenyList()

    @property
    def name(self) -> str:
        return "deny_list"

    @property
    def hook_point(self) -> HookPoint:
        return HookPoint.BEFORE_TOOL_EXECUTION

    @property
    def priority(self) -> int:
        return 10  # 最先执行

    async def execute(self, context: HookContext) -> HookResult:
        deny_result = self._deny_list.check(context.tool_name, context.tool_input)
        if deny_result.blocked:
            return HookResult(
                action=HookAction.ABORT,
                message=f"[DENIED] Gate 1 - Deny List: {deny_result.reason}",
            )
        return HookResult(action=HookAction.CONTINUE)
