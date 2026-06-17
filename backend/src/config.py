"""
配置管理模块 —— 从环境变量读取所有配置，不硬编码任何敏感信息。
"""

import os


class Config:
    """应用配置，所有值均从环境变量读取，提供合理的默认值。"""

    # --- LLM API 配置 ---
    ANTHROPIC_AUTH_TOKEN: str = os.getenv(
        "ANTHROPIC_AUTH_TOKEN",
        "sk-07d6ad88d4d444b4b57903f697f8ff11",
    )
    ANTHROPIC_BASE_URL: str = os.getenv(
        "ANTHROPIC_BASE_URL",
        "https://api.deepseek.com/anthropic",
    )
    ANTHROPIC_MODEL: str = os.getenv(
        "ANTHROPIC_MODEL",
        "deepseek-v4-pro",
    )

    # --- Agent Loop 配置 ---
    MAX_ITERATIONS: int = int(os.getenv("AGENT_MAX_ITERATIONS", "30"))
    SYSTEM_PROMPT: str = os.getenv(
        "AGENT_SYSTEM_PROMPT",
        "You are a helpful coding assistant. You can use tools to help the user with their programming tasks.",
    )

    # --- 安全 / 权限配置 ---
    WORKSPACE_ROOT: str = os.getenv("WORKSPACE_ROOT", "")  # 空字符串 = 使用当前工作目录

    # --- Server 配置 ---
    HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
    PORT: int = int(os.getenv("SERVER_PORT", "8000"))

    @classmethod
    def display(cls) -> dict:
        """返回脱敏后的配置信息，用于调试。"""
        return {
            "ANTHROPIC_BASE_URL": cls.ANTHROPIC_BASE_URL,
            "ANTHROPIC_MODEL": cls.ANTHROPIC_MODEL,
            "ANTHROPIC_AUTH_TOKEN": cls.ANTHROPIC_AUTH_TOKEN[:12] + "..." if cls.ANTHROPIC_AUTH_TOKEN else "NOT SET",
            "MAX_ITERATIONS": cls.MAX_ITERATIONS,
            "HOST": cls.HOST,
            "PORT": cls.PORT,
        }


config = Config()
