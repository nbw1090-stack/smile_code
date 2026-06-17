"""
任务列表存储 —— 进程内存中的任务状态管理。

提供任务的增删改查和进度展示。
每个任务有: id / subject / description / status(pending|in_progress|completed)

用法::

    store = TodoStore()
    store.upsert([
        {"id": "1", "subject": "实现登录", "status": "pending"},
        {"id": "2", "subject": "写测试", "status": "pending"},
    ])
    print(store.progress_display())
"""

from dataclasses import dataclass, field
from typing import Any

# 合法的任务状态
VALID_STATUSES = {"pending", "in_progress", "completed"}

# 终端颜色（ANSI）
_COLORS = {
    "pending": "\033[90m",       # 灰色
    "in_progress": "\033[93m",   # 黄色
    "completed": "\033[92m",     # 绿色
    "reset": "\033[0m",
    "bold": "\033[1m",
}

_STATUS_ICONS = {
    "pending": "⏳",
    "in_progress": "🔄",
    "completed": "✅",
}


@dataclass
class TodoItem:
    """单条任务。"""
    id: str
    subject: str
    description: str = ""
    status: str = "pending"

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "subject": self.subject,
            "description": self.description,
            "status": self.status,
        }


class TodoStore:
    """
    任务列表存储（进程内存）。

    线程安全：单线程 asyncio 环境下无需加锁。
    """

    def __init__(self) -> None:
        self._tasks: dict[str, TodoItem] = {}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def upsert(self, tasks: list[dict[str, Any]]) -> str:
        """
        批量创建或更新任务。

        参数 tasks 中每项包含:
            id: 任务唯一标识（必填）
            subject: 任务标题（必填）
            description: 任务描述（可选）
            status: pending | in_progress | completed（可选，默认 pending）

        返回:
            人类可读的进度摘要字符串
        """
        updated: list[str] = []
        created: list[str] = []

        for t in tasks:
            tid = t.get("id", "")
            if not tid:
                continue

            status = t.get("status", "pending")
            if status not in VALID_STATUSES:
                status = "pending"

            exists = tid in self._tasks

            item = TodoItem(
                id=tid,
                subject=t.get("subject", tid),
                description=t.get("description", ""),
                status=status,
            )
            self._tasks[tid] = item

            if exists:
                updated.append(tid)
            else:
                created.append(tid)

        parts: list[str] = []
        if created:
            parts.append(f"Created {len(created)} task(s): {', '.join(created)}")
        if updated:
            parts.append(f"Updated {len(updated)} task(s): {', '.join(updated)}")

        summary = "; ".join(parts) if parts else "No tasks changed"
        return f"{summary}\n\n{self.progress_display()}"

    def get(self, task_id: str) -> TodoItem | None:
        """获取单条任务。"""
        return self._tasks.get(task_id)

    def delete(self, task_id: str) -> bool:
        """删除任务。"""
        if task_id in self._tasks:
            del self._tasks[task_id]
            return True
        return False

    def list_all(self) -> list[TodoItem]:
        """返回所有任务列表。"""
        return list(self._tasks.values())

    def clear(self) -> None:
        """清空所有任务。"""
        self._tasks.clear()

    # ------------------------------------------------------------------
    # 进度展示
    # ------------------------------------------------------------------

    def progress_display(self) -> str:
        """
        生成带颜色的终端进度展示。

        示例输出::

            📋 任务进度: 1/3 完成

            ✅ [completed] 实现登录
            🔄 [in_progress] 写测试
            ⏳ [pending] 部署上线
        """
        tasks = list(self._tasks.values())
        if not tasks:
            return "📋 暂无任务"

        total = len(tasks)
        completed = sum(1 for t in tasks if t.status == "completed")
        in_progress = sum(1 for t in tasks if t.status == "in_progress")

        lines: list[str] = []
        lines.append(f"📋 任务进度: {completed}/{total} 完成"
                     + (f" (1 进行中)" if in_progress else ""))

        # 按状态排序: in_progress → pending → completed
        order = {"in_progress": 0, "pending": 1, "completed": 2}
        sorted_tasks = sorted(tasks, key=lambda t: order.get(t.status, 99))

        for t in sorted_tasks:
            icon = _STATUS_ICONS.get(t.status, "  ")
            color = _COLORS.get(t.status, "")
            line = f"  {icon} {color}[{t.status}]{_COLORS['reset']} {t.subject}"
            if t.description:
                line += f" — {t.description}"
            lines.append(line)

        return "\n".join(lines)

    def progress_summary(self) -> dict[str, int]:
        """返回进度统计数据。"""
        tasks = list(self._tasks.values())
        return {
            "total": len(tasks),
            "pending": sum(1 for t in tasks if t.status == "pending"),
            "in_progress": sum(1 for t in tasks if t.status == "in_progress"),
            "completed": sum(1 for t in tasks if t.status == "completed"),
        }
