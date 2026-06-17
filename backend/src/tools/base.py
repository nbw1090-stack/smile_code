"""
工具基类与工具注册表 —— 定义工具的抽象接口和注册管理。

每个工具必须提供:
- name: 工具名称（唯一标识）
- description: 工具描述
- input_schema: JSON Schema 格式的输入参数定义
- execute(**kwargs): 异步执行方法
"""

import traceback
from abc import ABC, abstractmethod
from typing import Any


# ---------------------------------------------------------------------------
# 工具基类
# ---------------------------------------------------------------------------

class BaseTool(ABC):
    """
    所有工具的抽象基类。

    子类需要实现:
        name       — 返回工具名称（str）
        description — 返回工具描述（str）
        input_schema — 返回输入参数的 JSON Schema（dict）
        execute    — 异步执行方法
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称，如 'read_file'、'execute_bash'。"""

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述，告知 LLM 该工具的功能。"""

    @property
    @abstractmethod
    def input_schema(self) -> dict[str, Any]:
        """输入参数的 JSON Schema 定义。"""

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """执行工具，返回字符串结果。"""

    def to_anthropic_format(self) -> dict[str, Any]:
        """转换为 Anthropic API 兼容的工具定义。"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


# ---------------------------------------------------------------------------
# 工具注册表
# ---------------------------------------------------------------------------

class ToolRegistry:
    """
    工具注册表 —— 管理所有可用工具的注册、查找和执行。

    用法::

        registry = ToolRegistry()
        registry.register(ReadFileTool())
        registry.register(ExecuteBashTool())

        # 获取 Anthropic 格式的工具列表
        tools = registry.get_tool_definitions()

        # 执行工具
        result = await registry.execute_tool("read_file", file_path="/path/to/file")
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    # ------------------------------------------------------------------
    # 注册管理
    # ------------------------------------------------------------------

    def register(self, tool: BaseTool) -> None:
        """注册一个工具实例。"""
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """移除一个已注册的工具。"""
        self._tools.pop(name, None)

    def get(self, name: str) -> BaseTool | None:
        """根据名称获取工具实例。"""
        return self._tools.get(name)

    def list_names(self) -> list[str]:
        """返回所有已注册工具的名称。"""
        return list(self._tools.keys())

    # ------------------------------------------------------------------
    # 格式转换
    # ------------------------------------------------------------------

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """获取所有工具的 Anthropic API 格式定义列表。"""
        return [tool.to_anthropic_format() for tool in self._tools.values()]

    # ------------------------------------------------------------------
    # 工具执行
    # ------------------------------------------------------------------

    async def execute_tool(self, tool_name: str, **kwargs: Any) -> str:
        """
        根据名称执行工具。

        参数:
            tool_name: 工具名称（注意：参数名不是 'name'，避免与工具自己的 'name' 参数冲突）
            **kwargs: 传递给工具 execute 方法的参数

        返回:
            工具执行结果字符串；若执行出错则返回包含错误信息的字符串
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            return f"Error: Unknown tool '{tool_name}'. Available tools: {self.list_names()}"

        try:
            result = await tool.execute(**kwargs)
            return result
        except Exception:
            return f"Error executing tool '{tool_name}':\n{traceback.format_exc()}"
