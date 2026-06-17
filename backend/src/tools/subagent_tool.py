"""
子 Agent 工具 —— SpawnSubagentTool

主 Agent 通过此工具派生子 Agent 执行独立子任务。

四个关键设计决策:
1. 上下文隔离  — 子 Agent 用全新的 messages[]，中间过程不污染主 Agent
2. 只回传结论  — 只返回子 Agent 最后一条文本，不回传整个 messages 列表
3. 禁止递归    — 子 Agent 的工具集不含 spawn_subagent，防止无限嵌套
4. 安全不跳过  — 子 Agent 的工具调用也走 before_tool_execution 钩子
"""

import logging
from typing import Any

from src.agent.agent_loop import AgentLoop
from src.agent.llm_client import LLMClient
from src.config import config
from src.hooks.base import HookManager
from src.tools.base import BaseTool, ToolRegistry
from src.tools.bash_tool import ExecuteBashTool
from src.tools.file_tools import ListFilesTool, ReadFileTool, WriteFileTool
from src.tools.todo_store import TodoStore
from src.tools.todo_tool import TodoWriteTool

logger = logging.getLogger(__name__)

# 子 Agent 专属系统提示词
_SUBAGENT_SYSTEM_PROMPT = """You are a sub-agent spawned by a parent coding agent to complete a specific subtask.

## Rules
1. Focus ONLY on the given task — do not go beyond scope.
2. Your final message IS the return value to the parent agent — be concise and factual.
3. You do NOT have the ability to spawn further sub-agents.
4. All your tool calls go through the same security checks as the parent agent.
5. Return raw data/answers, not conversational fluff."""


class SpawnSubagentTool(BaseTool):
    """
    派生子 Agent 执行独立子任务。

    用法（LLM 侧）::

        spawn_subagent(
            description="Read config files",
            prompt="Read config.yaml and config.json, return their merged content."
        )

    子 Agent 的约束:
    - 无 spawn_subagent 工具 → 不可递归
    - 共享安全钩子 → 权限不跳过
    - 全新消息上下文 → 不污染主 Agent
    """

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        hook_manager: HookManager | None = None,
        todo_store: TodoStore | None = None,
    ) -> None:
        self._llm = llm_client or LLMClient()
        self._hooks = hook_manager
        self._todo_store = todo_store

    @property
    def name(self) -> str:
        return "spawn_subagent"

    @property
    def description(self) -> str:
        return (
            "Spawn an isolated sub-agent to complete a standalone subtask. "
            "The sub-agent works with a clean context (no conversation history) "
            "and returns only its final conclusion.\n\n"
            "## When to Use\n"
            "- Complex multi-step research/find tasks where intermediate steps "
            "would clutter the main conversation\n"
            "- Independent parallel tasks (spawn multiple sub-agents concurrently)\n"
            "- Tasks that involve many tool calls but only the final result matters\n\n"
            "## Rules\n"
            "- Sub-agents CANNOT spawn further sub-agents\n"
            "- Sub-agents go through the SAME security checks as the parent\n"
            "- Sub-agents return ONLY their final text, not conversation history\n"
            "- The description should be a short 3-5 word label"
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "A short (3-5 word) description of the subtask.",
                },
                "prompt": {
                    "type": "string",
                    "description": "The complete task for the sub-agent to perform. "
                    "Be specific and include all context the sub-agent needs.",
                },
            },
            "required": ["description", "prompt"],
        }

    async def execute(self, description: str, prompt: str) -> str:
        """
        派生子 Agent 并执行。

        设计决策:
        1. 上下文隔离: 创建全新 AgentLoop → fresh messages[]
        2. 只回传结论: 仅返回 result["text"]
        3. 禁止递归: 子工具集不含 SpawnSubagentTool
        4. 安全不跳过: 共用 HookManager
        """
        logger.info(f"[SubAgent] Spawning: {description}")

        # ---- 构建子 Agent 的有限工具集（决策3: 无 spawn_subagent） ----
        sub_registry = ToolRegistry()
        sub_registry.register(ReadFileTool())
        sub_registry.register(WriteFileTool())
        sub_registry.register(ListFilesTool())
        sub_registry.register(ExecuteBashTool())
        if self._todo_store:
            sub_registry.register(TodoWriteTool(self._todo_store))

        # ---- 创建子 Agent（决策4: 共享安全钩子） ----
        sub_agent = _SubAgentLoop(
            tool_registry=sub_registry,
            llm_client=self._llm,
            hook_manager=self._hooks,  # 同一套钩子 → 安全不跳过
            system_prompt=_SUBAGENT_SYSTEM_PROMPT,
        )

        # ---- 执行（决策1: 全新上下文） ----
        try:
            result = await sub_agent.run(prompt)

            # ---- 决策2: 只回传结论 ----
            final_text = result.get("text", "")
            if not final_text:
                final_text = "(subagent completed with no output)"

            logger.info(
                f"[SubAgent] Done: {description} "
                f"(iterations={result.get('iterations', 0)}, "
                f"tools={result.get('tool_calls_made', [])})"
            )
            return final_text

        except Exception as exc:
            logger.error(f"[SubAgent] Failed: {description} — {exc}")
            return f"Subagent failed: {exc}"


# ---------------------------------------------------------------------------
# 内部子 Agent（轻量版 AgentLoop，固定 system_prompt）
# ---------------------------------------------------------------------------

class _SubAgentLoop(AgentLoop):
    """
    子 Agent 专用的 AgentLoop 变体。

    与父 AgentLoop 的唯一区别:
    - system_prompt 固定为子 Agent 专用提示词
    - 不可通过外部配置修改
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        llm_client: LLMClient,
        hook_manager: HookManager | None = None,
        system_prompt: str = "",
    ) -> None:
        super().__init__(tool_registry, hook_manager=hook_manager)
        self._llm = llm_client  # 共用父 Agent 的 LLM 客户端
        self._system_prompt = system_prompt or _SUBAGENT_SYSTEM_PROMPT
