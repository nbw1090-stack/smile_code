"""
CLI 主应用 —— REPL 循环，API 通信，审批交互。

用法::

    python -m src.cli.app
    # 或者
    python cli.py
"""

import asyncio
import atexit
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from src.cli.display import (
    console,
    show_agent_response,
    show_approval_needed,
    show_error,
    show_help,
    show_thinking,
    show_todo_progress,
    show_tool_call,
    show_tool_denied,
    show_tool_result,
    show_welcome,
)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

API_BASE = os.getenv("SMILE_API_BASE", "http://localhost:8000")
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# 后端进程管理
# ---------------------------------------------------------------------------

class BackendManager:
    """管理后端服务器的生命周期。"""

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None

    def start(self) -> None:
        """启动后端服务。"""
        # 检查是否已经在运行
        try:
            httpx.get(f"{API_BASE}/health", timeout=2)
            console.print("[dim]Backend already running.[/dim]")
            return
        except Exception:
            pass

        console.print("[dim]Starting backend server...[/dim]")
        venv_python = BACKEND_DIR / ".venv" / "bin" / "python"
        if not venv_python.exists():
            venv_python = Path(sys.executable)

        self._process = subprocess.Popen(
            [str(venv_python), "-m", "src.main"],
            cwd=str(BACKEND_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        atexit.register(self.stop)

        # 等待服务就绪
        for _ in range(30):
            time.sleep(0.3)
            try:
                r = httpx.get(f"{API_BASE}/health", timeout=2)
                if r.status_code == 200:
                    console.print("[dim]Backend ready.[/dim]")
                    return
            except Exception:
                pass
        console.print("[yellow]Backend may not be ready, continuing anyway...[/yellow]")

    def stop(self) -> None:
        """停止后端。"""
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None


# ---------------------------------------------------------------------------
# API 客户端
# ---------------------------------------------------------------------------

class APIClient:
    """与后端 REST API 通信。"""

    def __init__(self, base_url: str = API_BASE) -> None:
        self._base = base_url
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(300))

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self) -> dict:
        r = await self._client.get(f"{self._base}/health")
        r.raise_for_status()
        return r.json()

    async def chat(self, message: str) -> dict:
        """发送同步聊天请求。"""
        r = await self._client.post(
            f"{self._base}/chat",
            json={"message": message},
        )
        if r.status_code != 200:
            raise RuntimeError(f"API error {r.status_code}: {r.text[:200]}")
        return r.json()

    async def chat_stream(self, message: str):
        """流式聊天，逐行 yield JSON 事件。"""
        async with self._client.stream(
            "GET",
            f"{self._base}/chat/stream",
            params={"message": message},
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip():
                        try:
                            yield json.loads(data_str)
                        except json.JSONDecodeError:
                            pass

    async def approve(self, request_id: str, session_id: str, approved: bool) -> dict:
        """提交审批决策。"""
        r = await self._client.post(
            f"{self._base}/approve/{request_id}",
            params={"session_id": session_id},
            json={"approved": approved},
        )
        if r.status_code != 200:
            raise RuntimeError(f"Approve error {r.status_code}: {r.text[:200]}")
        return r.json()

    async def get_todo(self) -> dict:
        """获取任务进度。"""
        r = await self._client.get(f"{self._base}/todo")
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# REPL 应用
# ---------------------------------------------------------------------------

class CLIApp:
    """CLI 主 REPL 应用。"""

    def __init__(self) -> None:
        self._api = APIClient()
        self._running = True

    async def start(self) -> None:
        """入口：启动后端 → 获取健康信息 → 进入 REPL。"""
        # 尝试获取健康信息（后端可能已经在运行）
        try:
            health = await self._api.health()
            show_welcome(
                model=health.get("model", "?"),
                workspace=health.get("workspace_root", "?"),
            )
        except Exception:
            console.print("[yellow]Cannot reach backend. Starting it...[/yellow]")
            backend = BackendManager()
            backend.start()
            health = await self._api.health()
            show_welcome(
                model=health.get("model", "?"),
                workspace=health.get("workspace_root", "?"),
            )

        # 进入 REPL
        await self._repl()

    # ------------------------------------------------------------------
    # REPL
    # ------------------------------------------------------------------

    async def _repl(self) -> None:
        """主 REPL 循环。"""
        while self._running:
            try:
                # 圆角输入框：上半边框 + 输入行
                console.print()
                console.print("[bold cyan]╭─ You[/bold cyan]")
                user_input = await asyncio.to_thread(
                    console.input, "[bold cyan]╰─[/bold cyan][bold white]▸[/bold white] "
                )
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Goodbye.[/dim]")
                break

            user_input = user_input.strip()
            if not user_input:
                continue

            try:
                # 处理斜杠命令
                if user_input.startswith("/"):
                    await self._handle_command(user_input)
                else:
                    # 正常聊天
                    await self._handle_chat(user_input)
            except Exception as e:
                show_error(f"处理请求时出错: {e}")

    async def _handle_command(self, cmd: str) -> None:
        """处理 /slash 命令。"""
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()

        if command == "/exit" or command == "/quit":
            self._running = False
            console.print("[dim]Goodbye.[/dim]")
        elif command == "/help":
            show_help()
        elif command == "/todo":
            await self._show_todo()
        elif command == "/clear":
            console.clear()
        elif command == "/health":
            try:
                h = await self._api.health()
                console.print(f"Model: {h['model']}, Workspace: {h['workspace_root']}")
            except Exception as e:
                show_error(str(e))
        else:
            console.print(f"[dim]Unknown command: {command}. Type /help for available commands.[/dim]")

    async def _handle_chat(self, message: str) -> None:
        """处理一次聊天交互（支持流式和审批）。"""
        try:
            # 使用流式 API 获得实时工具调用展示
            await self._handle_streaming_chat(message)
        except Exception as e:
            show_error(str(e))

    async def _handle_streaming_chat(self, message: str) -> None:
        """流式聊天处理 —— 实时展示工具调用、审批、最终回复。"""
        thinking_shown = False
        session_id = ""

        try:
            async for event in self._api.chat_stream(message):
                etype = event.get("type", "")

                if etype == "state":
                    state = event.get("state", "")
                    if state == "thinking":
                        if not thinking_shown:
                            show_thinking()
                            thinking_shown = True

                elif etype == "tool_start":
                    if thinking_shown:
                        console.print(" " * 20, end="\r")  # 清除 thinking 行
                        thinking_shown = False
                    show_tool_call(event.get("tool", "?"), event.get("input", {}))

                elif etype == "tool_result":
                    show_tool_result(event.get("tool", "?"), event.get("result", ""))

                elif etype == "approval_needed":
                    # 流式模式下的审批：展示并询问用户
                    if thinking_shown:
                        console.print(" " * 20, end="\r")
                        thinking_shown = False
                    approved = show_approval_needed(
                        tool_name=event.get("tool_name", "?"),
                        reason=event.get("reason", ""),
                        rules=event.get("rules", []),
                    )
                    if approved:
                        console.print("  [green]✓ Allowed[/green]")
                    else:
                        console.print("  [red]✗ Denied[/red]")
                    # 流式模式暂不支持恢复执行，停止接收
                    console.print("  [dim](approval in streaming mode — resubmit with decision)[/dim]")
                    return

                elif etype == "text":
                    if thinking_shown:
                        console.print(" " * 20, end="\r")
                        thinking_shown = False
                    show_agent_response(event.get("text", ""))

                elif etype == "error":
                    if thinking_shown:
                        console.print(" " * 20, end="\r")
                        thinking_shown = False
                    show_error(event.get("error", "Unknown error"))

                elif etype == "done":
                    if thinking_shown:
                        console.print(" " * 20, end="\r")
                        thinking_shown = False
                    status = event.get("status", "done")
                    if status == "error":
                        show_error(event.get("text", "")[:200])
                    elif status == "done" and event.get("text"):
                        pass  # text already shown

        except httpx.RemoteProtocolError:
            # SSE 连接中断（可能是 LLM 返回格式问题），回退到同步 API
            console.print("[dim]Stream interrupted, using sync fallback...[/dim]")
            await self._handle_sync_chat(message)

    async def _handle_sync_chat(self, message: str) -> None:
        """同步聊天回退（处理审批流程）。"""
        result = await self._api.chat(message)
        pending = result.get("approval")

        while pending:
            # 展示审批请求
            approved = show_approval_needed(
                tool_name=pending.get("tool_name", "?"),
                reason=pending.get("reason", ""),
                rules=pending.get("rules", []),
            )

            # 提交决策
            result = await self._api.approve(
                request_id=pending.get("request_id", ""),
                session_id=result.get("session_id", ""),
                approved=approved,
            )
            pending = result.get("approval")

        # 展示最终回复
        if result.get("status") == "error":
            show_error(result.get("text", "")[:300])
        elif result.get("text"):
            show_agent_response(result.get("text", ""))

    async def _show_todo(self) -> None:
        """展示任务进度。"""
        try:
            data = await self._api.get_todo()
            show_todo_progress(data)
        except Exception as e:
            show_error(str(e))


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

async def main() -> None:
    """CLI 入口。"""
    # 处理 Ctrl+C
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: None)
        except NotImplementedError:
            pass

    backend = BackendManager()
    backend.start()

    app = CLIApp()
    try:
        await app.start()
    finally:
        await app._api.close()
        backend.stop()


if __name__ == "__main__":
    asyncio.run(main())
