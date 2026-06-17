"""
TodoStore 和 TodoWriteTool 测试。

运行::

    cd backend && source .venv/bin/activate
    python -m pytest tests/test_todo.py -v
"""

import pytest

from src.tools.todo_store import TodoStore, TodoItem
from src.tools.todo_tool import TodoWriteTool


class TestTodoStore:
    """TodoStore 单元测试。"""

    @pytest.fixture
    def store(self):
        return TodoStore()

    def test_upsert_creates_tasks(self, store):
        result = store.upsert([
            {"id": "1", "subject": "Task 1", "status": "pending"},
            {"id": "2", "subject": "Task 2", "status": "pending"},
        ])
        assert "Created 2" in result
        assert len(store.list_all()) == 2

    def test_upsert_updates_existing(self, store):
        store.upsert([{"id": "1", "subject": "Task 1", "status": "pending"}])
        result = store.upsert([{"id": "1", "subject": "Task 1", "status": "completed"}])
        assert "Updated 1" in result
        assert store.get("1").status == "completed"

    def test_upsert_replace_all(self, store):
        """每次调用 upsert 会覆盖整个列表（包含所有的任务）。"""
        store.upsert([
            {"id": "1", "subject": "A", "status": "pending"},
            {"id": "2", "subject": "B", "status": "pending"},
        ])
        # 第二次调用只列了 task 1，task 2 仍保留（upsert 不删除旧任务）
        store.upsert([{"id": "1", "subject": "A", "status": "completed"}])
        assert len(store.list_all()) == 2  # task 2 还在
        assert store.get("1").status == "completed"

    def test_invalid_status_defaults_to_pending(self, store):
        store.upsert([{"id": "1", "subject": "X", "status": "invalid"}])
        assert store.get("1").status == "pending"

    def test_get_nonexistent(self, store):
        assert store.get("nope") is None

    def test_delete(self, store):
        store.upsert([{"id": "1", "subject": "X", "status": "pending"}])
        assert store.delete("1")
        assert store.get("1") is None
        assert not store.delete("1")

    def test_clear(self, store):
        store.upsert([
            {"id": "1", "subject": "A", "status": "pending"},
            {"id": "2", "subject": "B", "status": "completed"},
        ])
        store.clear()
        assert len(store.list_all()) == 0

    def test_progress_summary(self, store):
        store.upsert([
            {"id": "1", "subject": "A", "status": "completed"},
            {"id": "2", "subject": "B", "status": "in_progress"},
            {"id": "3", "subject": "C", "status": "pending"},
            {"id": "4", "subject": "D", "status": "pending"},
        ])
        s = store.progress_summary()
        assert s["total"] == 4
        assert s["completed"] == 1
        assert s["in_progress"] == 1
        assert s["pending"] == 2

    def test_progress_display_empty(self, store):
        assert "暂无任务" in store.progress_display()

    def test_progress_display_has_colors(self, store):
        store.upsert([
            {"id": "1", "subject": "Done task", "status": "completed"},
            {"id": "2", "subject": "Active task", "status": "in_progress"},
            {"id": "3", "subject": "Todo task", "status": "pending"},
        ])
        display = store.progress_display()
        assert "📋" in display
        assert "1/3" in display
        assert "Done task" in display
        assert "Active task" in display
        assert "Todo task" in display

    def test_typical_flow(self, store):
        """模拟 Agent 典型任务流程。"""
        # 第一步：列出所有步骤
        result = store.upsert([
            {"id": "1", "subject": "读需求", "status": "pending"},
            {"id": "2", "subject": "写代码", "status": "pending"},
            {"id": "3", "subject": "写测试", "status": "pending"},
        ])
        assert "Created 3" in result

        # 第二步：开始做第一个
        store.upsert([
            {"id": "1", "subject": "读需求", "status": "in_progress"},
            {"id": "2", "subject": "写代码", "status": "pending"},
            {"id": "3", "subject": "写测试", "status": "pending"},
        ])
        assert store.get("1").status == "in_progress"
        s = store.progress_summary()
        assert s["in_progress"] == 1
        assert s["pending"] == 2

        # 第三步：完成第一个，开始第二个
        store.upsert([
            {"id": "1", "subject": "读需求", "status": "completed"},
            {"id": "2", "subject": "写代码", "status": "in_progress"},
            {"id": "3", "subject": "写测试", "status": "pending"},
        ])
        assert store.get("1").status == "completed"
        assert store.get("2").status == "in_progress"

        # 第四步：全部完成
        store.upsert([
            {"id": "1", "subject": "读需求", "status": "completed"},
            {"id": "2", "subject": "写代码", "status": "completed"},
            {"id": "3", "subject": "写测试", "status": "completed"},
        ])
        s = store.progress_summary()
        assert s["completed"] == 3
        assert s["total"] == 3


class TestTodoWriteTool:
    """TodoWriteTool 单元测试。"""

    @pytest.fixture
    def store(self):
        return TodoStore()

    @pytest.fixture
    def tool(self, store):
        return TodoWriteTool(store)

    def test_tool_name(self, tool):
        assert tool.name == "todo_write"

    def test_input_schema(self, tool):
        schema = tool.input_schema
        assert schema["type"] == "object"
        assert "tasks" in schema["properties"]

    def test_to_anthropic_format(self, tool):
        fmt = tool.to_anthropic_format()
        assert fmt["name"] == "todo_write"
        assert "input_schema" in fmt

    @pytest.mark.asyncio
    async def test_execute(self, tool):
        result = await tool.execute([
            {"id": "1", "subject": "任务一", "status": "pending"},
            {"id": "2", "subject": "任务二", "status": "pending"},
        ])
        assert "Created 2" in result
        assert "📋" in result
        assert "0/2" in result
