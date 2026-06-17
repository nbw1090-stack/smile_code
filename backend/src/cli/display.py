"""
CLI 显示工具 —— Rich 终端渲染。

提供:
- 彩色面板、状态指示器
- 工具调用展示
- 审批请求展示
- 任务进度展示
- Markdown 渲染
"""

from rich.console import Console
from rich.markup import escape as rich_escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.markdown import Markdown

console = Console()

# 颜色常量
COLOR_TOOL = "cyan"
COLOR_DENIED = "red"
COLOR_APPROVAL = "yellow"
COLOR_DONE = "green"
COLOR_ERROR = "red"
COLOR_THINKING = "dim"
COLOR_USER = "bold white"

# 图标
ICON_USER = "▸"
ICON_AGENT = "◆"
ICON_TOOL = "🔧"
ICON_DENIED = "🚫"
ICON_APPROVAL = "⚠️"
ICON_DONE = "✓"
ICON_ERROR = "✗"
ICON_SPINNER = "◌"


def show_welcome(model: str, workspace: str) -> None:
    """启动欢迎信息。"""
    console.print()
    console.print(
        Panel(
            f"[bold]Smile Code Agent[/bold]\n"
            f"Model: [dim]{model}[/dim]\n"
            f"Workspace: [dim]{workspace}[/dim]\n\n"
            f"Type [bold]/help[/bold] for commands, [bold]/exit[/bold] to quit.",
            border_style="bold",
            padding=(1, 2),
        )
    )
    console.print()


def show_user_message(text: str) -> None:
    """用户消息。"""
    # 转义用户输入中的 Rich 标记语法，防止 [xxx] 被误解析导致崩溃
    escaped = rich_escape(text)
    console.print(f"[{COLOR_USER}]{ICON_USER} {escaped}[/{COLOR_USER}]")


def show_thinking() -> None:
    """正在思考指示器。"""
    console.print(f"[{COLOR_THINKING}]  thinking...[/{COLOR_THINKING}]", end="\r")


def show_tool_call(tool_name: str, tool_input: dict) -> None:
    """工具调用开始。"""
    short_input = _truncate(str(tool_input), 80)
    console.print(f"  [{COLOR_TOOL}]{ICON_TOOL} {rich_escape(tool_name)}[/{COLOR_TOOL}] [dim]{rich_escape(short_input)}[/dim]")


def show_tool_result(tool_name: str, result: str) -> None:
    """工具调用结果。"""
    short = _truncate(result, 120)
    console.print(f"    [{COLOR_DONE}]{ICON_DONE} {rich_escape(short)}[/{COLOR_DONE}]")


def show_tool_denied(tool_name: str, reason: str) -> None:
    """闸门1 拒绝。"""
    console.print(f"  [{COLOR_DENIED}]{ICON_DENIED} DENIED: {rich_escape(tool_name)}[/{COLOR_DENIED}]")
    console.print(f"    [dim]{rich_escape(reason)}[/dim]")


def show_approval_needed(tool_name: str, reason: str, rules: list) -> bool:
    """闸门2 审批请求。暂停并询问用户。返回 True=允许。"""
    console.print()
    console.print(
        Panel(
            f"[bold {COLOR_APPROVAL}]{ICON_APPROVAL} Approval Required[/bold {COLOR_APPROVAL}]\n\n"
            f"Tool: [bold]{rich_escape(tool_name)}[/bold]\n"
            f"Reason: {rich_escape(reason)}",
            border_style=COLOR_APPROVAL,
            padding=(1, 2),
        )
    )

    if rules:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style="dim")
        table.add_column()
        for r in rules:
            sev_color = "red" if r.get("severity") == "critical" else "yellow"
            table.add_row(f"[{sev_color}]{rich_escape(r.get('severity', ''))}[/{sev_color}]", rich_escape(r.get("description", "")))
        console.print(table)

    console.print()
    try:
        answer = input(f"  Allow? [y/N] ").strip().lower()
        return answer in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def show_agent_response(text: str) -> None:
    """Agent 最终回复。"""
    console.print()
    try:
        md = Markdown(text)
        console.print(md)
    except Exception:
        console.print(text)
    console.print()


def show_todo_progress(data: dict) -> None:
    """任务进度展示。"""
    summary = data.get("summary", {})
    tasks = data.get("tasks", [])

    total = summary.get("total", 0)
    completed = summary.get("completed", 0)
    in_progress = summary.get("in_progress", 0)

    status_line = f"📋 {completed}/{total} done"
    if in_progress:
        status_line += f" (1 in progress)"
    console.print(f"[bold]{status_line}[/bold]")

    if tasks:
        icons = {"completed": "✅", "in_progress": "🔄", "pending": "⏳"}
        colors = {"completed": "green", "in_progress": "yellow", "pending": "dim"}
        for t in tasks:
            s = t.get("status", "pending")
            icon = icons.get(s, "  ")
            color = colors.get(s, "")
            console.print(f"  {icon} [{color}][{rich_escape(s)}][/{color}] {rich_escape(t.get('subject', ''))}")


def show_error(text: str) -> None:
    """错误信息。"""
    console.print(f"\n[{COLOR_ERROR}]{ICON_ERROR} {rich_escape(str(text))}[/{COLOR_ERROR}]\n")


def show_help() -> None:
    """帮助信息。"""
    console.print()
    console.print(
        Panel(
            "[bold]Commands[/bold]\n\n"
            "  [bold]/help[/bold]    Show this help\n"
            "  [bold]/todo[/bold]    Show task progress\n"
            "  [bold]/clear[/bold]   Clear screen\n"
            "  [bold]/exit[/bold]    Quit\n\n"
            "Type any message to chat with the agent.\n"
            "Ctrl+C to interrupt.",
            border_style="dim",
            padding=(1, 2),
        )
    )
    console.print()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."
