"""提供 Pydantic 结构化数据模型；本文件负责 `api` 相关实现。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UserContext(BaseModel):
    """定义 `UserContext` 使用的结构化数据。"""

    user_id: str


class SessionCreateRequest(BaseModel):
    """定义创建聊天会话时允许提交的字段。"""
    title: str | None = None


class SessionResponse(BaseModel):
    """定义 会话 响应的数据结构。"""
    session_id: str
    user_id: str
    title: str | None = None
    current_trip_id: str | None = None
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MessageCreateRequest(BaseModel):
    """定义发送一条用户消息时的请求结构。"""
    message: str = Field(min_length=1, max_length=8000)


class MessageResponse(BaseModel):
    """定义 消息 响应的数据结构。"""
    message_id: str
    session_id: str
    user_id: str
    role: str
    content: str
    created_at: datetime | None = None


class WorkflowResponse(BaseModel):
    """定义 工作流 响应的数据结构。"""
    session_id: str
    request_id: str | None
    response: str
    node_trace: list[str] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    execution_elapsed_seconds: float | None = None


class TripResponse(BaseModel):
    """定义 旅行 响应的数据结构。"""
    trip_id: str
    user_id: str
    session_id: str
    destination: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    status: str
    current_version: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class TripVersionResponse(BaseModel):
    """定义 旅行、版本 响应的数据结构。"""
    version_id: str
    trip_id: str
    user_id: str
    version_number: int
    itinerary: dict[str, Any]
    change_reason: str | None = None
    source_agent: str | None = None
    created_at: datetime | None = None


class MemoryResponse(BaseModel):
    """定义 记忆 响应的数据结构。"""
    memory_id: str
    memory_type: str
    category: str
    statement: str
    scope: str
    polarity: str
    importance: float
    confidence: float
    evidence_count: int
    status: str
    has_embedding: bool = False


class MemoryUpdateRequest(BaseModel):
    """定义用户修改长期记忆陈述时的请求结构。"""
    statement: str


class MemorySettingsRequest(BaseModel):
    """定义 记忆、设置 请求的数据结构。"""
    personalization_enabled: bool | None = None
    long_term_memory_enabled: bool | None = None


class HealthResponse(BaseModel):
    """定义 健康状态 响应的数据结构。"""
    status: str = "ok"
    service: str = "travelmind-api"
    database: bool = False
