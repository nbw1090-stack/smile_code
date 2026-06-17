"""
钩子系统基础 —— 定义钩子接口、上下文、结果和管理器。

钩子机制允许在不同阶段插入自定义逻辑。每个钩子有:
- hook_point: 在哪个阶段触发
- priority: 执行优先级（数字越小越先执行）
- execute(context): 钩子逻辑，返回 HookResult
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# 钩子阶段
# ---------------------------------------------------------------------------

class HookPoint(str, Enum):
    """钩子触发阶段。"""
    BEFORE_TOOL_EXECUTION = "before_tool_execution"
    AFTER_TOOL_EXECUTION = "after_tool_execution"
    BEFORE_LLM_CALL = "before_llm_call"
    AFTER_LLM_CALL = "after_llm_call"


# ---------------------------------------------------------------------------
# 钩子结果
# ---------------------------------------------------------------------------

class HookAction(str, Enum):
    """钩子返回的动作。"""
    CONTINUE = "continue"              # 继续（执行下一个钩子或执行工具）
    ABORT = "abort"                    # 中止（拒绝执行）
    NEEDS_APPROVAL = "needs_approval"  # 需要用户审批


@dataclass
class HookResult:
    """钩子执行结果。"""
    action: HookAction = HookAction.CONTINUE
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 钩子上下文
# ---------------------------------------------------------------------------

@dataclass
class HookContext:
    """
    传递给钩子的上下文信息。

    各阶段可用字段:
    - before_tool_execution: tool_name, tool_input, tool_use_id
    - after_tool_execution:   tool_name, tool_input, execution_result
    - before_llm_call:       messages, tools, system_prompt
    - after_llm_call:         messages, response
    """
    tool_name: str = ""
    tool_input: dict[str, Any] = field(default_factory=dict)
    tool_use_id: str = ""
    execution_result: str = ""
    messages: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    system_prompt: str = ""


# ---------------------------------------------------------------------------
# 钩子基类
# ---------------------------------------------------------------------------

class BaseHook(ABC):
    """
    所有钩子的抽象基类。

    子类需要实现:
        name       — 钩子名称
        hook_point — 触发阶段
        priority   — 优先级（越小越先执行，默认 100）
        execute    — 钩子逻辑
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """钩子唯一名称。"""

    @property
    @abstractmethod
    def hook_point(self) -> HookPoint:
        """钩子触发阶段。"""

    @property
    def priority(self) -> int:
        """优先级，数字越小越先执行。默认 100。"""
        return 100

    @abstractmethod
    async def execute(self, context: HookContext) -> HookResult:
        """执行钩子逻辑。"""


# ---------------------------------------------------------------------------
# 钩子管理器
# ---------------------------------------------------------------------------

class HookManager:
    """
    钩子管理器 —— 注册、排序、执行钩子。

    用法::

        manager = HookManager()
        manager.register(DenyListHook(deny_list))
        manager.register(RuleEngineHook(rule_engine, workspace))

        result = await manager.run_hooks(HookPoint.BEFORE_TOOL_EXECUTION, context)
        if result.action == HookAction.ABORT:
            ...
    """

    def __init__(self) -> None:
        self._hooks: dict[HookPoint, list[BaseHook]] = {
            hp: [] for hp in HookPoint
        }

    def register(self, hook: BaseHook) -> None:
        """注册一个钩子。"""
        self._hooks[hook.hook_point].append(hook)
        # 按 priority 排序
        self._hooks[hook.hook_point].sort(key=lambda h: h.priority)

    def unregister(self, name: str) -> None:
        """根据名称移除钩子。"""
        for hp in HookPoint:
            self._hooks[hp] = [h for h in self._hooks[hp] if h.name != name]

    def list_hooks(self) -> dict[str, list[str]]:
        """列出所有已注册的钩子。"""
        result: dict[str, list[str]] = {}
        for hp in HookPoint:
            hooks = self._hooks[hp]
            result[hp.value] = [f"{h.name}(p={h.priority})" for h in hooks]
        return result

    async def run_hooks(
        self,
        hook_point: HookPoint,
        context: HookContext,
    ) -> HookResult:
        """
        按优先级顺序执行指定阶段的所有钩子。

        任一钩子返回 ABORT 或 NEEDS_APPROVAL 时立即短路返回，
        后续钩子不再执行。

        返回:
            HookResult —— 如果所有钩子都返回 CONTINUE，则返回 CONTINUE
        """
        for hook in self._hooks[hook_point]:
            result = await hook.execute(context)
            if result.action != HookAction.CONTINUE:
                return result
        return HookResult(action=HookAction.CONTINUE)

    # ------------------------------------------------------------------
    # 审批辅助（从 PermissionManager 搬过来）
    # ------------------------------------------------------------------

    def get_pending_request(self, request_id: str) -> dict[str, Any] | None:
        """
        遍历所有钩子查找待审批请求详情。

        由 NEEDS_APPROVAL 的钩子存储审批上下文。
        """
        for hooks in self._hooks.values():
            for hook in hooks:
                if hasattr(hook, "get_pending_request"):
                    detail = hook.get_pending_request(request_id)
                    if detail is not None:
                        return detail
        return None

    def approve(self, request_id: str, approved: bool) -> bool:
        """提交审批决策。"""
        for hooks in self._hooks.values():
            for hook in hooks:
                if hasattr(hook, "approve"):
                    if hook.approve(request_id, approved):
                        return True
        return False

    async def wait_for_approval(
        self, request_id: str, timeout: float | None = None
    ) -> bool:
        """等待审批决策（异步阻塞）。"""
        for hooks in self._hooks.values():
            for hook in hooks:
                if hasattr(hook, "wait_for_approval"):
                    return await hook.wait_for_approval(request_id, timeout=timeout)
        return False
