"""
API 层的请求/响应数据模型（Pydantic）。

所有与外部通信的数据结构均在此定义，确保类型安全。
"""

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    """POST /chat 的请求体。"""
    message: str = Field(..., description="用户输入的消息文本", min_length=1)


class ApproveRequest(BaseModel):
    """POST /approve/{request_id} 的请求体。"""
    approved: bool = Field(..., description="True=允许执行, False=拒绝执行")


# ---------------------------------------------------------------------------
# 审批详情模型
# ---------------------------------------------------------------------------

class RuleDetail(BaseModel):
    """单条规则的命中详情。"""
    rule_name: str
    severity: str
    description: str
    detail: dict = Field(default_factory=dict)


class ApprovalInfo(BaseModel):
    """审批请求的详细信息（前端展示用）。"""
    request_id: str
    tool_name: str
    tool_input: dict
    reason: str
    rules: list[RuleDetail]


# ---------------------------------------------------------------------------
# 响应模型
# ---------------------------------------------------------------------------

class ChatResponse(BaseModel):
    """POST /chat 的响应体。"""
    session_id: str = Field(..., description="会话 ID，用于后续审批操作")
    status: str = Field(..., description="运行状态: done | error | awaiting_approval")
    text: str = Field(default="", description="Agent 的最终文本回复")
    iterations: int = Field(default=0, description="实际迭代次数")
    tool_calls_made: list[str] = Field(default_factory=list)
    approval: ApprovalInfo | None = Field(default=None, description="审批请求详情（status=awaiting_approval 时有效）")


class ApproveResponse(BaseModel):
    """POST /approve/{request_id} 的响应体。"""
    session_id: str
    status: str = Field(..., description="运行状态: done | error | awaiting_approval")
    text: str = Field(default="")
    iterations: int = Field(default=0)
    tool_calls_made: list[str] = Field(default_factory=list)
    approval: ApprovalInfo | None = Field(default=None)


class HealthResponse(BaseModel):
    """健康检查响应。"""
    status: str = "ok"
    model: str
    base_url: str
    workspace_root: str
