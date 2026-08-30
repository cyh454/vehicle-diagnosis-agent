"""API 请求/响应模型。"""
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000, description="工程师输入")
    session_id: str | None = Field(None, description="会话ID，首次对话可不传")
    user_id: str = Field("anonymous", description="工程师标识")


class ToolCallInfo(BaseModel):
    tool: str
    input: dict | str | None = None
    output: str | None = None


class VehicleBrief(BaseModel):
    vin: str | None = None
    brand: str
    model: str
    year: int | None = None
    power_type: str | None = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    vehicle: VehicleBrief | None = None
    tool_calls: list[ToolCallInfo] = []
    latency_ms: int
    created: bool = False


class MessageItem(BaseModel):
    role: str
    content: str
    tool_calls: list | None = None
    latency_ms: int | None = None
    created_at: str | None = None


class SessionBrief(BaseModel):
    """会话列表条目（侧边栏用）。"""
    session_id: str
    title: str | None = None
    message_count: int = 0
    vehicle: VehicleBrief | None = None
    updated_at: str | None = None


class SessionDetail(BaseModel):
    session_id: str
    user_id: str
    vehicle: VehicleBrief | None = None
    title: str | None = None
    message_count: int
    messages: list[MessageItem] = []
