"""
Agent Loop 核心引擎 —— 驱动 LLM 与工具之间的多轮交互循环。

核心流程::

    user_input → [LLM] → text? → 返回最终结果
                     ↓
                  tool_use? → before_tool 钩子 → 执行工具 → after_tool 钩子
                              ↓
                         闸门1/2/3 检查
                              ↓
                    追加结果 → [LLM] → ...

安全限制:
- MAX_ITERATIONS: 防止无限循环
- 钩子系统: 通过 before_tool_execution 钩子实现三道闸门
"""

import asyncio
import logging
from typing import Any, AsyncIterator

from src.agent.llm_client import LLMClient, Message, LLMClientError
from src.config import config
from src.hooks.base import HookAction, HookContext, HookManager, HookPoint
from src.tools.base import ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Agent 状态枚举
# ---------------------------------------------------------------------------

class AgentState:
    """Agent 运行状态常量。"""
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    AWAITING_APPROVAL = "awaiting_approval"
    DONE = "done"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Agent Loop
# ---------------------------------------------------------------------------

class AgentLoop:
    """
    Coding Agent 的主循环引擎。

    通过 HookManager 在不同阶段触发钩子:
    - before_tool_execution: 权限检查（闸门1拒绝列表 → 闸门2规则引擎）
    - after_tool_execution:  日志/审计（可扩展）

    用法::

        agent = AgentLoop(tool_registry, hook_manager)
        result = await agent.run("列出当前目录的文件")
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        hook_manager: HookManager | None = None,
    ) -> None:
        self._llm = LLMClient()
        self._tools = tool_registry
        self._hooks = hook_manager or HookManager()
        self._system_prompt = config.SYSTEM_PROMPT
        self._max_iterations = config.MAX_ITERATIONS

    @property
    def hook_manager(self) -> HookManager:
        return self._hooks

    # ------------------------------------------------------------------
    # 同步（非流式）运行
    # ------------------------------------------------------------------

    async def run(
        self,
        user_message: str,
        result_future: asyncio.Future | None = None,
    ) -> dict[str, Any]:
        """运行一次完整的 Agent Loop。"""
        messages: list[Message] = []
        tools = self._tools.get_tool_definitions()
        tool_calls_made: list[str] = []

        messages.append(LLMClient.build_user_message(user_message))

        result = await self._run_loop(messages, tools, tool_calls_made)

        if result_future and not result_future.done():
            result_future.set_result(result)

        return result

    # ------------------------------------------------------------------
    # 从挂起点恢复
    # ------------------------------------------------------------------

    async def resume_after_approval(
        self,
        request_id: str,
        messages: list[Message],
        tools: list[dict[str, Any]],
        tool_calls_made: list[str],
        pending_tool_uses: list[dict[str, Any]],
        result_future: asyncio.Future | None = None,
    ) -> dict[str, Any]:
        """审批通过后恢复执行。"""
        for tool_use in pending_tool_uses:
            tool_name = tool_use.get("name", "unknown")
            tool_input = tool_use.get("input", {})
            tool_use_id = tool_use.get("id", "")

            logger.info(f"[AgentLoop] Resumed: executing {tool_name}")
            tool_calls_made.append(tool_name)

            exec_result = await self._tools.execute_tool(tool_name, **tool_input)
            messages.append(
                LLMClient.build_tool_result_message(tool_use_id, exec_result)
            )

        result = await self._run_loop(messages, tools, tool_calls_made)

        if result_future and not result_future.done():
            result_future.set_result(result)

        return result

    # ------------------------------------------------------------------
    # 流式运行
    # ------------------------------------------------------------------

    async def run_stream(self, user_message: str) -> AsyncIterator[dict[str, Any]]:
        """流式运行 Agent Loop（SSE 事件流）。"""
        messages: list[Message] = []
        tools = self._tools.get_tool_definitions()
        tool_calls_made: list[str] = []

        messages.append(LLMClient.build_user_message(user_message))

        yield {"type": "state", "state": AgentState.THINKING}

        iteration = 0
        final_text = ""

        while iteration < self._max_iterations:
            iteration += 1

            try:
                response = await self._llm.chat(
                    messages=messages, tools=tools, system=self._system_prompt,
                )
            except LLMClientError as exc:
                yield {"type": "error", "error": str(exc)}
                break

            messages.append(response)
            tool_uses = LLMClient.get_tool_uses(response)

            if not tool_uses:
                final_text = LLMClient.get_text_content(response)
                yield {"type": "text", "text": final_text}
                break

            yield {"type": "state", "state": AgentState.EXECUTING}

            tool_results: list[dict[str, Any]] = []

            for tool_use in tool_uses:
                tool_name = tool_use.get("name", "unknown")
                tool_input = tool_use.get("input", {})
                tool_use_id = tool_use.get("id", "")

                tool_calls_made.append(tool_name)
                yield {"type": "tool_start", "tool": tool_name, "input": tool_input}

                hook_result = await self._run_before_tool_hooks(
                    tool_name, tool_input, tool_use_id
                )

                if hook_result.get("type") == "approval_needed":
                    yield hook_result
                    tool_result_text = f"[REJECTED] Approval required."
                elif hook_result.get("type") == "tool_result":
                    yield hook_result
                    tool_result_text = hook_result["result"]
                else:
                    tool_result_text = hook_result.get("result", "")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": tool_result_text,
                })

            messages.append({"role": "user", "content": tool_results})

            yield {"type": "state", "state": AgentState.THINKING}

        else:
            final_text = f"Reached maximum iterations ({self._max_iterations})."

        yield {
            "type": "done", "status": AgentState.DONE,
            "text": final_text, "iterations": iteration,
            "tool_calls_made": tool_calls_made,
        }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    async def _run_loop(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        tool_calls_made: list[str],
    ) -> dict[str, Any]:
        """主循环逻辑。"""
        iteration = 0
        final_text = ""

        while iteration < self._max_iterations:
            iteration += 1
            logger.info(f"[AgentLoop] Iteration {iteration}/{self._max_iterations}")

            try:
                response = await self._llm.chat(
                    messages=messages, tools=tools, system=self._system_prompt,
                )
            except LLMClientError as exc:
                logger.error(f"[AgentLoop] LLM error: {exc}")
                final_text = f"LLM call failed: {exc}"
                break

            messages.append(response)
            tool_uses = LLMClient.get_tool_uses(response)

            if not tool_uses:
                final_text = LLMClient.get_text_content(response)
                break

            # 收集所有 tool_result，最后打包成一条 user 消息
            tool_results: list[dict[str, Any]] = []

            for tool_use in tool_uses:
                tool_name = tool_use.get("name", "unknown")
                tool_input = tool_use.get("input", {})
                tool_use_id = tool_use.get("id", "")

                logger.info(f"[AgentLoop] Executing tool: {tool_name}")
                tool_calls_made.append(tool_name)

                hook_result = await self._run_before_tool_hooks(
                    tool_name, tool_input, tool_use_id
                )

                # 闸门1 拒绝
                if hook_result.get("type") == "aborted":
                    msg = hook_result["result"]
                    logger.warning(f"[AgentLoop] {msg}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": msg,
                    })
                    continue

                # 闸门2 命中 → 挂起等审批
                if hook_result.get("type") == "approval_needed":
                    return {
                        "status": AgentState.AWAITING_APPROVAL,
                        "text": "", "iterations": iteration,
                        "tool_calls_made": tool_calls_made,
                        "approval": {
                            "request_id": hook_result["request_id"],
                            "tool_name": hook_result["tool_name"],
                            "tool_input": hook_result["tool_input"],
                            "rules": hook_result["rules"],
                            "reason": hook_result["reason"],
                        },
                        "_messages": messages,
                        "_tools": tools,
                        "_tool_calls_made": tool_calls_made,
                        "_pending_tool_uses": [tool_use],
                    }

                # 通过 → 执行
                exec_result = await self._tools.execute_tool(tool_name, **tool_input)

                # 执行后钩子
                await self._run_after_tool_hooks(
                    tool_name, tool_input, tool_use_id, exec_result
                )

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": exec_result,
                })

            # 所有 tool_result 打包进一条 user 消息
            messages.append({
                "role": "user",
                "content": tool_results,
            })

        else:
            final_text = f"Reached maximum iterations ({self._max_iterations})."

        return {
            "status": (
                AgentState.DONE
                if not final_text.startswith(("LLM call failed", "Reached maximum"))
                else AgentState.ERROR
            ),
            "text": final_text, "iterations": iteration,
            "tool_calls_made": tool_calls_made,
        }

    async def _run_before_tool_hooks(
        self, tool_name: str, tool_input: dict, tool_use_id: str
    ) -> dict[str, Any]:
        """执行 before_tool_execution 阶段的钩子。"""
        ctx = HookContext(
            tool_name=tool_name,
            tool_input=tool_input,
            tool_use_id=tool_use_id,
        )
        result = await self._hooks.run_hooks(HookPoint.BEFORE_TOOL_EXECUTION, ctx)

        if result.action == HookAction.ABORT:
            return {"type": "aborted", "result": result.message}

        if result.action == HookAction.NEEDS_APPROVAL:
            return {
                "type": "approval_needed",
                "request_id": result.data.get("request_id", ""),
                "tool_name": result.data.get("tool_name", tool_name),
                "tool_input": result.data.get("tool_input", tool_input),
                "reason": result.message,
                "rules": result.data.get("rules", []),
            }

        return {"type": "allowed"}

    async def _run_after_tool_hooks(
        self, tool_name: str, tool_input: dict,
        tool_use_id: str, exec_result: str,
    ) -> None:
        """执行 after_tool_execution 阶段的钩子。"""
        ctx = HookContext(
            tool_name=tool_name,
            tool_input=tool_input,
            tool_use_id=tool_use_id,
            execution_result=exec_result,
        )
        await self._hooks.run_hooks(HookPoint.AFTER_TOOL_EXECUTION, ctx)
