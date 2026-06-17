"""
API 路由定义 —— 提供 REST 和 SSE 两种接口。

端点:
- GET  /health                  健康检查
- POST /chat                    同步聊天（支持审批挂起/恢复）
- GET  /chat/stream             流式聊天（SSE）
- POST /approve/{request_id}    提交审批决策（恢复 Agent Loop）
- GET  /approve/{request_id}    查询审批请求详情
"""

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from src.agent.agent_loop import AgentLoop, AgentState
from src.agent.llm_client import LLMClient
from src.api.schemas import (
    ApproveRequest,
    ApproveResponse,
    ApprovalInfo,
    ChatRequest,
    ChatResponse,
    HealthResponse,
    RuleDetail,
)
from src.config import config

logger = logging.getLogger(__name__)

router = APIRouter()

# Agent 和 SessionStore 实例 —— 在 app 启动时由 main.py 注入
_agent: AgentLoop | None = None
_session_store = None  # SessionStore 实例


def set_agent(agent: AgentLoop) -> None:
    """注入 AgentLoop 实例（由 main.py 在启动时调用）。"""
    global _agent
    _agent = agent


def set_session_store(store) -> None:
    """注入 SessionStore 实例（由 main.py 在启动时调用）。"""
    global _session_store
    _session_store = store


def _get_agent() -> AgentLoop:
    """获取 AgentLoop 实例，若未初始化则抛出异常。"""
    if _agent is None:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    return _agent


def _build_chat_response(
    sid: str, result: dict, approval: ApprovalInfo | None = None
) -> ChatResponse:
    """从 Agent Loop 结果构建 ChatResponse。"""
    return ChatResponse(
        session_id=sid,
        status=result.get("status", AgentState.ERROR),
        text=result.get("text", ""),
        iterations=result.get("iterations", 0),
        tool_calls_made=result.get("tool_calls_made", []),
        approval=approval,
    )


def _extract_approval(result: dict) -> ApprovalInfo | None:
    """从 Agent Loop 结果中提取审批信息。"""
    if result.get("status") != AgentState.AWAITING_APPROVAL:
        return None
    approval_data = result.get("approval", {})
    if not approval_data:
        return None
    return ApprovalInfo(
        request_id=approval_data.get("request_id", ""),
        tool_name=approval_data.get("tool_name", ""),
        tool_input=approval_data.get("tool_input", {}),
        reason=approval_data.get("reason", ""),
        rules=[RuleDetail(**r) for r in approval_data.get("rules", [])],
    )


async def _run_agent_in_session(
    sid: str,
    agent: AgentLoop,
    user_message: str | None = None,
    resume_ctx: dict | None = None,
) -> ChatResponse:
    """
    在会话中执行 Agent Loop（可能是首次运行或审批后恢复）。

    - 首次运行: user_message 有值, resume_ctx 为 None
    - 审批恢复: user_message 为 None, resume_ctx 包含挂起状态
    """
    loop = asyncio.get_event_loop()

    if resume_ctx is not None:
        # 审批后恢复执行
        future: asyncio.Future = loop.create_future()
        session = _session_store.get(sid)
        if session:
            session.result_future = future

        result = await agent.resume_after_approval(
            request_id=resume_ctx["approval_request_id"],
            messages=resume_ctx["messages"],
            tools=resume_ctx["tools"],
            tool_calls_made=resume_ctx["tool_calls_made"],
            pending_tool_uses=resume_ctx["pending_tool_uses"],
        )
        approval = _extract_approval(result)

        if approval:
            # 再次挂起 —— 更新 session 的 resume_state（session 保持不删）
            session = _session_store.get(sid)
            if session:
                session.resume_state = {
                    "messages": result.get("_messages", []),
                    "tools": result.get("_tools", []),
                    "tool_calls_made": result.get("_tool_calls_made", []),
                    "pending_tool_uses": result.get("_pending_tool_uses", []),
                    "approval_request_id": approval.request_id,
                }

        return _build_chat_response(sid, result, approval)

    else:
        # 首次运行
        future: asyncio.Future = loop.create_future()
        session = _session_store.get(sid)
        if session:
            session.result_future = future

        async def _bg_run():
            try:
                r = await agent.run(user_message)
                if not future.done():
                    future.set_result(r)
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)

        asyncio.create_task(_bg_run())

        try:
            result = await asyncio.wait_for(
                asyncio.shield(future),
                timeout=config.MAX_ITERATIONS * 60,
            )
        except asyncio.TimeoutError:
            _session_store.remove(sid)
            raise HTTPException(status_code=504, detail="Agent request timed out")

        approval = _extract_approval(result)

        if approval:
            # 挂起 —— 保存恢复状态到 session（session 保持不删）
            session = _session_store.get(sid)
            if session:
                session.resume_state = {
                    "messages": result.get("_messages", []),
                    "tools": result.get("_tools", []),
                    "tool_calls_made": result.get("_tool_calls_made", []),
                    "pending_tool_uses": result.get("_pending_tool_uses", []),
                    "approval_request_id": approval.request_id,
                }

        return _build_chat_response(sid, result, approval)


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """服务健康检查。"""
    agent = _get_agent()
    ws_root = "N/A"
    return HealthResponse(
        model=config.ANTHROPIC_MODEL,
        base_url=config.ANTHROPIC_BASE_URL,
        workspace_root=ws_root,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    同步聊天 —— 支持审批流程。

    流程:
    1. 创建会话，运行 Agent Loop
    2. 如果正常完成 → 返回 status="done"
    3. 如果需要审批 → 返回 status="awaiting_approval" + approval 详情
    4. 前端调用 POST /approve/{request_id}?session_id=xxx 提交决策
    """
    agent = _get_agent()
    logger.info(f"[API] /chat: {request.message[:80]}...")

    sid, _ = _session_store.create_session()
    return await _run_agent_in_session(sid, agent, user_message=request.message)


@router.get("/approve/{request_id}")
async def get_approval_detail(request_id: str):
    """
    查询待审批请求的详细信息（前端展示用）。
    """
    agent = _get_agent()
    hm = agent.hook_manager

    detail = hm.get_pending_request(request_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=f"Approval request '{request_id}' not found or already resolved",
        )
    return detail


@router.post("/approve/{request_id}", response_model=ChatResponse)
async def approve(
    request_id: str,
    body: ApproveRequest,
    session_id: str = Query(..., description="原始 /chat 返回的 session_id"),
):
    """
    提交审批决策，恢复 Agent Loop 执行。

    - approved=true  → 执行被挂起的工具调用，Agent Loop 继续
    - approved=false → 跳过该工具调用，告知 LLM 操作被拒绝
    """
    agent = _get_agent()
    hm = agent.hook_manager

    # 查找挂起的 session
    session = _session_store.get(session_id)
    if session is None or session.resume_state is None:
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found or not in approval state",
        )

    # 验证 request_id 匹配
    if session.resume_state.get("approval_request_id") != request_id:
        raise HTTPException(
            status_code=400,
            detail=f"Request ID '{request_id}' does not match session's pending approval "
            f"'{session.resume_state.get('approval_request_id')}'",
        )

    resume_ctx = session.resume_state

    # 提交闸门3 决策
    hm.approve(request_id, body.approved)

    if not body.approved:
        # 用户拒绝 → 将拒绝信息作为工具结果加入消息，然后继续循环
        pending_tool_uses = resume_ctx.get("pending_tool_uses", [])
        messages = resume_ctx.get("messages", [])
        tools = resume_ctx.get("tools", [])
        tool_calls_made = resume_ctx.get("tool_calls_made", [])

        for tool_use in pending_tool_uses:
            tool_use_id = tool_use.get("id", "")
            messages.append(
                LLMClient.build_tool_result_message(
                    tool_use_id,
                    f"[REJECTED] User denied this operation.",
                )
            )

        # 创建一个新的 session 来恢复循环
        sid, _ = _session_store.create_session()
        # 直接调用 resume（用空 pending_tool_uses 表示工具已被跳过）
        result = await agent.resume_after_approval(
            request_id=request_id,
            messages=messages,
            tools=tools,
            tool_calls_made=tool_calls_made,
            pending_tool_uses=[],  # 空 = 跳过执行
        )
        approval = _extract_approval(result)
        if approval:
            new_session = _session_store.get(sid)
            if new_session:
                new_session.resume_state = {
                    "messages": result.get("_messages", []),
                    "tools": result.get("_tools", []),
                    "tool_calls_made": result.get("_tool_calls_made", []),
                    "pending_tool_uses": result.get("_pending_tool_uses", []),
                    "approval_request_id": approval.request_id,
                }
            _session_store.remove(sid)
        return _build_chat_response(sid, result, approval)

    else:
        # 用户允许 → 恢复执行
        return await _run_agent_in_session(
            session_id, agent, resume_ctx=resume_ctx
        )


@router.get("/todo")
async def get_todo_progress():
    """查询当前任务列表进度。"""
    from src.main import get_todo_store
    store = get_todo_store()
    return {
        "tasks": [t.to_dict() for t in store.list_all()],
        "summary": store.progress_summary(),
        "display": store.progress_display(),
    }


@router.get("/chat/stream")
async def chat_stream(message: str = Query(..., description="用户输入的消息")):
    """
    流式聊天（SSE）—— 实时推送 Agent 的思考、工具调用、结果等事件。
    流式模式下的审批请求会以 approval_needed 事件推送。
    """
    agent = _get_agent()
    logger.info(f"[API] /chat/stream: {message[:80]}...")

    async def event_generator():
        async for event in agent.run_stream(message):
            yield {"data": json.dumps(event, ensure_ascii=False)}

    return EventSourceResponse(event_generator())
