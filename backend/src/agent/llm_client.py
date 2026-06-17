"""
LLM 客户端封装 —— 封装 Anthropic SDK，统一处理消息发送和响应解析。

职责：
- 封装 AsyncAnthropic 客户端
- 将内部消息格式转换为 API 请求
- 解析响应中的文本和 tool_use
- 不关心 Agent Loop 逻辑（由 agent_loop.py 负责）
"""

from typing import Any

from anthropic import AsyncAnthropic

from src.config import config


# ---------------------------------------------------------------------------
# 自定义异常
# ---------------------------------------------------------------------------

class LLMClientError(Exception):
    """LLM 客户端调用失败时抛出。"""


# ---------------------------------------------------------------------------
# 类型定义
# ---------------------------------------------------------------------------

# 一条消息的简化格式，兼容 Anthropic messages API 的 content block 类型
Message = dict[str, Any]          # {"role": "user|assistant", "content": [...]}
ToolDefinition = dict[str, Any]   # Anthropic tool 定义（JSON Schema）


# ---------------------------------------------------------------------------
# LLM 客户端
# ---------------------------------------------------------------------------

class LLMClient:
    """
    LLM 客户端，封装对 DeepSeek/Anthropic API 的调用。

    用法::

        client = LLMClient()
        response = await client.chat(
            messages=[...],
            tools=[...],
            system="You are a helpful assistant.",
        )
    """

    def __init__(self) -> None:
        self._client = AsyncAnthropic(
            api_key=config.ANTHROPIC_AUTH_TOKEN,
            base_url=config.ANTHROPIC_BASE_URL,
        )
        self._model = config.ANTHROPIC_MODEL

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[Message],
        tools: list[ToolDefinition] | None = None,
        system: str | None = None,
    ) -> Message:
        """
        发送消息到 LLM，返回 assistant 消息。

        参数:
            messages: 对话历史，每条消息格式为 Anthropic messages API 的
                      ``{"role": "...", "content": [...]}``
            tools: 工具定义列表（可为 None 或空列表）
            system: 系统提示词（可选）

        返回:
            assistant 消息，content 中可能包含 text 或 tool_use block

        异常:
            LLMClientError: API 调用失败时抛出
        """
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        if system:
            kwargs["system"] = system

        try:
            response = await self._client.messages.create(**kwargs)
        except Exception as exc:
            raise LLMClientError(f"LLM API call failed: {exc}") from exc

        # 构造标准化的 assistant 消息
        return {
            "role": "assistant",
            "content": self._parse_content_blocks(response.content),
        }

    # ------------------------------------------------------------------
    # 静态工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def build_user_message(text: str) -> Message:
        """将纯文本构建为 user 消息。"""
        return {
            "role": "user",
            "content": [{"type": "text", "text": text}],
        }

    @staticmethod
    def build_tool_result_message(
        tool_use_id: str,
        result: str,
        is_error: bool = False,
    ) -> Message:
        """构建 tool_result 消息。"""
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": result,
                    "is_error": is_error,
                }
            ],
        }

    @staticmethod
    def get_text_content(message: Message) -> str:
        """从 assistant 消息中提取纯文本内容。"""
        texts: list[str] = []
        for block in message.get("content", []):
            if block.get("type") == "text":
                texts.append(block.get("text", ""))
        return "\n".join(texts)

    @staticmethod
    def get_tool_uses(message: Message) -> list[dict[str, Any]]:
        """从 assistant 消息中提取所有 tool_use block。"""
        return [
            block
            for block in message.get("content", [])
            if block.get("type") == "tool_use"
        ]

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_content_blocks(blocks: list[Any]) -> list[dict[str, Any]]:
        """
        将 Anthropic SDK 返回的 content block 对象列表转换为普通 dict 列表。

        兼容 TextBlock / ToolUseBlock / 纯 dict 三种格式。
        """
        parsed: list[dict[str, Any]] = []
        for block in blocks:
            if hasattr(block, "model_dump"):
                parsed.append(block.model_dump())
            elif isinstance(block, dict):
                parsed.append(block)
            else:
                parsed.append({"type": "text", "text": str(block)})
        return parsed
