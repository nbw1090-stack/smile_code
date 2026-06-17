"""
Agent Loop 单元测试与集成测试。

运行方式::

    cd backend
    python -m pytest tests/ -v
"""

import asyncio
import pytest

from src.tools.base import BaseTool, ToolRegistry
from src.agent.llm_client import LLMClient


# ---------------------------------------------------------------------------
# 工具系统测试
# ---------------------------------------------------------------------------

class _EchoTool(BaseTool):
    """测试用工具 —— 回显输入。"""

    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echo back the input."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to echo"},
            },
            "required": ["text"],
        }

    async def execute(self, text: str) -> str:
        return f"ECHO: {text}"


class _FailingTool(BaseTool):
    """测试用工具 —— 总是抛出异常。"""

    @property
    def name(self) -> str:
        return "failer"

    @property
    def description(self) -> str:
        return "Always fails."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(self) -> str:
        raise RuntimeError("Intentional failure")


class TestToolRegistry:
    """ToolRegistry 单元测试。"""

    def test_register_and_get(self):
        registry = ToolRegistry()
        tool = _EchoTool()
        registry.register(tool)
        assert registry.get("echo") is tool

    def test_register_duplicate_raises(self):
        registry = ToolRegistry()
        registry.register(_EchoTool())
        with pytest.raises(ValueError, match="already registered"):
            registry.register(_EchoTool())

    def test_unregister(self):
        registry = ToolRegistry()
        registry.register(_EchoTool())
        registry.unregister("echo")
        assert registry.get("echo") is None

    def test_list_names(self):
        registry = ToolRegistry()
        registry.register(_EchoTool())
        registry.register(_FailingTool())
        assert sorted(registry.list_names()) == ["echo", "failer"]

    def test_get_tool_definitions(self):
        registry = ToolRegistry()
        registry.register(_EchoTool())
        defs = registry.get_tool_definitions()
        assert len(defs) == 1
        assert defs[0]["name"] == "echo"
        assert "input_schema" in defs[0]

    @pytest.mark.asyncio
    async def test_execute_tool(self):
        registry = ToolRegistry()
        registry.register(_EchoTool())
        result = await registry.execute_tool("echo", text="hello")
        assert result == "ECHO: hello"

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        registry = ToolRegistry()
        result = await registry.execute_tool("nonexistent")
        assert "Unknown tool" in result

    @pytest.mark.asyncio
    async def test_execute_failing_tool(self):
        registry = ToolRegistry()
        registry.register(_FailingTool())
        result = await registry.execute_tool("failer")
        assert "Error executing tool" in result


# ---------------------------------------------------------------------------
# LLM 客户端辅助方法测试
# ---------------------------------------------------------------------------

class TestLLMClientHelpers:
    """LLMClient 静态方法的单元测试。"""

    def test_build_user_message(self):
        msg = LLMClient.build_user_message("hello")
        assert msg["role"] == "user"
        assert msg["content"][0]["type"] == "text"
        assert msg["content"][0]["text"] == "hello"

    def test_build_tool_result_message(self):
        msg = LLMClient.build_tool_result_message("tu_123", "result text")
        assert msg["role"] == "user"
        assert msg["content"][0]["type"] == "tool_result"
        assert msg["content"][0]["tool_use_id"] == "tu_123"
        assert msg["content"][0]["content"] == "result text"

    def test_get_text_content(self):
        msg = {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Hello!"},
                {"type": "text", "text": "World!"},
            ],
        }
        assert LLMClient.get_text_content(msg) == "Hello!\nWorld!"

    def test_get_tool_uses(self):
        msg = {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me check."},
                {"type": "tool_use", "id": "tu_1", "name": "read_file", "input": {"file_path": "/x"}},
            ],
        }
        tool_uses = LLMClient.get_tool_uses(msg)
        assert len(tool_uses) == 1
        assert tool_uses[0]["name"] == "read_file"

    def test_get_tool_uses_none(self):
        msg = {"role": "assistant", "content": [{"type": "text", "text": "Done."}]}
        assert LLMClient.get_tool_uses(msg) == []
