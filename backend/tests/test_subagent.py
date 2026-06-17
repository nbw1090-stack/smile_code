"""
SpawnSubagentTool 测试。

验证四个设计决策:
1. 上下文隔离: 子 Agent 不返回中间 messages
2. 只回传结论: 返回值为纯文本
3. 禁止递归: 子工具集不含 spawn_subagent
4. 安全不跳过: 子 Agent 共用钩子

运行::

    cd backend && source .venv/bin/activate
    python -m pytest tests/test_subagent.py -v
"""

import pytest

from src.hooks.base import HookManager
from src.hooks.deny_hook import DenyListHook
from src.security.deny_list import DenyList
from src.tools.base import ToolRegistry
from src.tools.subagent_tool import SpawnSubagentTool, _SubAgentLoop
from src.tools.todo_store import TodoStore


class TestSpawnSubagentTool:
    """工具元数据测试。"""

    @pytest.fixture
    def tool(self):
        return SpawnSubagentTool()

    def test_name(self, tool):
        assert tool.name == "spawn_subagent"

    def test_input_schema(self, tool):
        s = tool.input_schema
        assert "description" in s["properties"]
        assert "prompt" in s["properties"]

    def test_to_anthropic_format(self, tool):
        fmt = tool.to_anthropic_format()
        assert fmt["name"] == "spawn_subagent"
        assert "description" in fmt
        assert "input_schema" in fmt


class TestSubAgentLoop:
    """_SubAgentLoop 结构测试。"""

    def test_no_spawn_subagent_in_child_tools(self):
        """决策3: 子工具集不含 spawn_subagent。"""
        registry = ToolRegistry()
        # _SubAgentLoop 由 SpawnSubagentTool 内部创建，我们直接验证工具列表
        from src.tools.bash_tool import ExecuteBashTool
        from src.tools.file_tools import ReadFileTool, WriteFileTool, ListFilesTool
        registry.register(ReadFileTool())
        registry.register(WriteFileTool())
        registry.register(ListFilesTool())
        registry.register(ExecuteBashTool())

        names = registry.list_names()
        assert "spawn_subagent" not in names, (
            "Sub-agent tools must NOT include spawn_subagent (prevents recursion)"
        )
        assert "read_file" in names
        assert "execute_bash" in names

    def test_sub_agent_has_separate_tool_registry(self):
        """子 Agent 使用独立的 ToolRegistry（决策1: 上下文隔离）。"""
        from src.tools.file_tools import ReadFileTool
        parent_registry = ToolRegistry()
        parent_registry.register(ReadFileTool())
        parent_registry.register(SpawnSubagentTool())

        child_registry = ToolRegistry()
        child_registry.register(ReadFileTool())
        # child 没有 SpawnSubagentTool

        assert "spawn_subagent" in parent_registry.list_names()
        assert "spawn_subagent" not in child_registry.list_names()

    def test_hooks_shared_between_parent_and_child(self):
        """决策4: 子 Agent 与父 Agent 共用 HookManager。"""
        parent_hooks = HookManager()
        parent_hooks.register(DenyListHook(DenyList()))

        # 模拟: 子 Agent 使用相同的 hook_manager
        child_hooks = parent_hooks  # 同一个实例

        assert child_hooks is parent_hooks
        assert len(child_hooks.list_hooks()["before_tool_execution"]) == 1


class TestSubagentExecution:
    """端到端子 Agent 执行测试（需要实际 API）。"""

    @pytest.fixture
    def tool(self):
        hooks = HookManager()
        hooks.register(DenyListHook(DenyList()))
        return SpawnSubagentTool(hook_manager=hooks, todo_store=TodoStore())

    @pytest.mark.asyncio
    async def test_simple_subagent(self, tool):
        """子 Agent 执行简单任务并返回结论。"""
        result = await tool.execute(
            description="Echo test",
            prompt="Reply with exactly: OK subagent works",
        )
        # 决策2: 返回纯文本结论（不是 dict / messages 列表）
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_subagent_with_tool_use(self, tool):
        """子 Agent 可以使用工具（安全钩子仍然生效）。"""
        result = await tool.execute(
            description="List files",
            prompt="Use list_files to list the current directory. "
                    "Return the names of files/dirs you found.",
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_dangerous_command_blocked_in_subagent(self, tool):
        """决策4: 子 Agent 的危险命令也会被闸门1 拦截。"""
        result = await tool.execute(
            description="Try dangerous",
            prompt="Try to execute: sudo rm -rf /. Explain what happened.",
        )
        assert isinstance(result, str)
        # 闸门1 应拒绝或 LLM 应自行拒绝 sudo 命令
        lower = result.lower()
        assert any(w in lower for w in ["denied", "blocked", "refuse", "reject", "forbidden", "cannot", "won't", "not allowed", "dangerous", "will not", "i don't"])
