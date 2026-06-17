"""
Shell 执行工具 —— 执行 bash 命令并返回结果。

安全说明:
- 命令在工作目录下执行
- 超时保护（默认 120 秒）
- 不支持交互式命令
"""

import asyncio
import os
from typing import Any

from src.tools.base import BaseTool


class ExecuteBashTool(BaseTool):
    """在 shell 中执行命令并返回 stdout + stderr。"""

    # 默认工作目录
    _WORK_DIR: str = os.getcwd()

    @property
    def name(self) -> str:
        return "execute_bash"

    @property
    def description(self) -> str:
        return (
            "Execute a bash command and return its output (stdout and stderr). "
            "Use this to run shell commands like ls, grep, git, npm, pip, etc. "
            "The command runs in a non-interactive shell with a 120-second timeout."
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The bash command to execute.",
                },
            },
            "required": ["command"],
        }

    async def execute(self, command: str) -> str:
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._WORK_DIR,
                env=os.environ.copy(),
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=120.0,
            )

            out_text = stdout.decode("utf-8", errors="replace")
            err_text = stderr.decode("utf-8", errors="replace")

            parts: list[str] = []
            if out_text.strip():
                parts.append(out_text.strip())
            if err_text.strip():
                parts.append(f"[stderr]\n{err_text.strip()}")
            if process.returncode is not None and process.returncode != 0:
                parts.append(f"[exit code: {process.returncode}]")

            return "\n".join(parts) if parts else "(no output)"

        except asyncio.TimeoutError:
            return "Error: Command timed out after 120 seconds."
        except Exception as exc:
            return f"Error executing command: {exc}"

    @classmethod
    def set_work_dir(cls, path: str) -> None:
        """设置命令执行的工作目录。"""
        cls._WORK_DIR = path
