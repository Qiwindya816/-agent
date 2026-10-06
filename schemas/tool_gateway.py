"""提供 Pydantic 结构化数据模型；本文件负责 `tool_gateway` 相关实现。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field


class ToolDescriptor(BaseModel):
    """定义 `ToolDescriptor` 使用的结构化数据。"""

    name: str
    description: str
    provider: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    cache_ttl_seconds: int = 0
    timeout_seconds: int = 30
    retry_count: int = 0
    result_expires_in_seconds: int | None = None


class ProviderDescriptor(BaseModel):
    """定义 `ProviderDescriptor` 使用的结构化数据。"""

    name: str
    status: str = "unknown"
    circuit_state: str = "closed"
    success_rate: float = 1.0
    average_latency: float = 0.0
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None


class GatewayCallContext(BaseModel):
    """定义 `GatewayCallContext` 使用的结构化数据。"""

    user_id: str
    session_id: str | None = None
    trip_id: str | None = None
    request_id: str | None = None


class ToolCallSnapshot(BaseModel):
    """定义 `ToolCallSnapshot` 使用的结构化数据。"""

    tool_call_id: str
    provider: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    status: str
    error_code: str | None = None
    latency_ms: int
    retries: int = 0
    cache_hit: bool = False
    created_at: datetime


def expiry_from_now(seconds: int | None, now: datetime | None = None) -> datetime | None:
    """计算过期时间 `expiry_from_now` 对应的数据和流程，返回该步骤的处理结果。"""
    if seconds is None:
        return None
    current = now or datetime.now()
    return current + timedelta(seconds=seconds)
