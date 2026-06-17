"""
任务列表工具 —— TodoWriteTool

提供给 LLM 调用的 todo_write 工具。
LLM 通过调用此工具来创建、更新任务状态，终端会展示彩色进度。

典型流程::

    Agent 收到任务
    → todo_write: 列出所有步骤（全 pending）
    → 做一个步骤，把该步骤改成 in_progress
    → 做完后改成 completed
    → 看下一个 pending 步骤 → 继续
"""

from typing import Any

from src.tools.base import BaseTool
from src.tools.todo_store import TodoStore


class TodoWriteTool(BaseTool):
    """
    todo_write 工具 —— 创建和更新结构化任务列表。

    LLM 调用此工具来跟踪进度。任务状态流转:
    pending → in_progress → completed
    """

    def __init__(self, store: TodoStore | None = None) -> None:
        self._store = store or TodoStore()

    @property
    def name(self) -> str:
        return "todo_write"

    @property
    def description(self) -> str:
        return (
            "Create and update a structured task list for your current coding session. "
            "Use this to track progress, organize complex tasks, and demonstrate thoroughness.\n\n"
            "## When to Use\n"
            "Use proactively for:\n"
            "- Complex multi-step tasks (3+ distinct steps)\n"
            "- User provides multiple tasks (numbered/comma-separated)\n"
            "- After receiving new instructions — capture requirements as tasks\n"
            "- When you start working on a task — mark it in_progress FIRST\n"
            "- IMMEDIATELY after COMPLETING a task — mark it completed\n\n"
            "## Task States\n"
            "- pending: not yet started\n"
            "- in_progress: currently working on (ONLY ONE at a time)\n"
            "- completed: finished successfully\n\n"
            "## Typical Flow\n"
            "1. First call: list ALL steps as pending\n"
            "2. Mark one task in_progress → do the work\n"
            "3. Mark it completed → pick next pending → repeat\n\n"
            "## Rules\n"
            "- ALWAYS include ALL tasks in each call (not just the changed one) — "
            "this overwrites the list\n"
            "- Only ONE task in_progress at a time\n"
            "- Mark completed ONLY when FULLY done (tests pass, no errors)\n"
            "- Do NOT mark completed if tests fail or implementation is partial"
        )

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tasks": {
                    "type": "array",
                    "description": (
                        "The complete task list. ALWAYS include ALL tasks, not just changed ones. "
                        "Each task must have: id (unique identifier string), "
                        "subject (brief imperative title), "
                        "description (optional, what needs to be done), "
                        "status (one of: pending, in_progress, completed)."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {
                                "type": "string",
                                "description": "Unique identifier for this task (e.g. '1', 'setup-db').",
                            },
                            "subject": {
                                "type": "string",
                                "description": "Brief imperative title (e.g. 'Implement login').",
                            },
                            "description": {
                                "type": "string",
                                "description": "What needs to be done.",
                            },
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                                "description": "Current status of this task.",
                            },
                        },
                        "required": ["id", "subject", "status"],
                    },
                },
            },
            "required": ["tasks"],
        }

    async def execute(self, tasks: list[dict[str, Any]]) -> str:
        """
        执行任务列表更新。

        参数:
            tasks: 完整的任务列表，每项含 id/subject/description/status

        返回:
            终端格式的进度展示字符串
        """
        return self._store.upsert(tasks)

    @property
    def store(self) -> TodoStore:
        """获取底层存储（供外部查询进度）。"""
        return self._store
