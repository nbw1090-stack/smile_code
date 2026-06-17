"""
文件操作工具 —— 提供文件读写能力。

工具:
- read_file: 读取指定文件内容
- write_file: 写入内容到指定文件
"""

import os
from pathlib import Path
from typing import Any

from src.tools.base import BaseTool


# ---------------------------------------------------------------------------
# 读取文件工具
# ---------------------------------------------------------------------------

class ReadFileTool(BaseTool):
    """读取指定文件的内容。"""

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read the contents of a file at the given path. Returns the file content as a string."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The absolute path to the file to read.",
                },
            },
            "required": ["file_path"],
        }

    async def execute(self, file_path: str) -> str:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            return f"Error: File not found: {file_path}"
        if path.is_dir():
            return f"Error: Path is a directory, not a file: {file_path}"
        try:
            content = path.read_text(encoding="utf-8")
            # 限制返回长度，避免撑爆上下文
            if len(content) > 50000:
                content = content[:50000] + "\n\n... [content truncated at 50000 characters]"
            return content
        except Exception as exc:
            return f"Error reading file: {exc}"


# ---------------------------------------------------------------------------
# 写入文件工具
# ---------------------------------------------------------------------------

class WriteFileTool(BaseTool):
    """写入内容到指定文件（会覆盖已有文件）。"""

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write content to a file at the given path. Overwrites the file if it already exists."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The absolute path to the file to write to.",
                },
                "content": {
                    "type": "string",
                    "description": "The content to write to the file.",
                },
            },
            "required": ["file_path", "content"],
        }

    async def execute(self, file_path: str, content: str) -> str:
        path = Path(file_path).expanduser().resolve()
        try:
            # 确保父目录存在
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return f"Successfully wrote {len(content)} characters to {file_path}"
        except Exception as exc:
            return f"Error writing file: {exc}"


# ---------------------------------------------------------------------------
# 列出目录文件工具
# ---------------------------------------------------------------------------

class ListFilesTool(BaseTool):
    """列出目录中的文件和子目录。"""

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return "List files and directories in the given directory path."

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "dir_path": {
                    "type": "string",
                    "description": "The absolute path to the directory to list.",
                },
            },
            "required": ["dir_path"],
        }

    async def execute(self, dir_path: str) -> str:
        path = Path(dir_path).expanduser().resolve()
        if not path.exists():
            return f"Error: Directory not found: {dir_path}"
        if not path.is_dir():
            return f"Error: Path is not a directory: {dir_path}"
        try:
            items = sorted(path.iterdir())
            lines = []
            for item in items:
                suffix = "/" if item.is_dir() else ""
                lines.append(f"  {item.name}{suffix}")
            return "\n".join(lines) if lines else "(empty directory)"
        except Exception as exc:
            return f"Error listing directory: {exc}"
