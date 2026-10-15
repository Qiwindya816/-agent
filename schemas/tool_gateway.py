"""提供 Pydantic 结构化数据模型；本文件负责 `tool_gateway` 相关实现。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field


class ToolDescriptor(BaseModel):
    """定义 `ToolDescriptor` 使用的结构化数据。"""

    name: str  # 工具名
    description: str  # 描述
    provider: str  # 提供方
    input_schema: dict[str, Any] = Field(default_factory=dict)  # 输入 Schema
    output_schema: dict[str, Any] = Field(default_factory=dict)  # 输出 Schema
    cache_ttl_seconds: int = 0  # 缓存 TTL
    timeout_seconds: int = 30  # 超时秒数
    retry_count: int = 0  # 重试次数
    result_expires_in_seconds: int | None = None  # 结果有效期


class ProviderDescriptor(BaseModel):
    """定义 `ProviderDescriptor` 使用的结构化数据。"""

    name: str  # Provider 名称
    status: str = "unknown"  # 状态
    circuit_state: str = "closed"  # 熔断状态
    success_rate: float = 1.0  # 成功率
    average_latency: float = 0.0  # 平均延迟
    last_success_at: datetime | None = None  # 最近成功时间
    last_failure_at: datetime | None = None  # 最近失败时间


class GatewayCallContext(BaseModel):
    """定义 `GatewayCallContext` 使用的结构化数据。"""

    user_id: str  # 用户 ID
    session_id: str | None = None  # 会话 ID
    trip_id: str | None = None  # 行程 ID
    request_id: str | None = None  # 请求 ID


class ToolCallSnapshot(BaseModel):
    """定义 `ToolCallSnapshot` 使用的结构化数据。"""

    tool_call_id: str  # 调用 ID
    provider: str  # 提供方
    tool_name: str  # 工具名
    arguments: dict[str, Any] = Field(default_factory=dict)  # 输入参数
    result: dict[str, Any] | None = None  # 返回结果
    status: str  # 状态
    error_code: str | None = None  # 错误码
    latency_ms: int  # 耗时毫秒
    retries: int = 0  # 重试次数
    cache_hit: bool = False  # 是否缓存命中
    created_at: datetime  # 时间


def expiry_from_now(seconds: int | None, now: datetime | None = None) -> datetime | None:
    """计算过期时间 `expiry_from_now` 对应的数据和流程，返回该步骤的处理结果。"""
    if seconds is None:
        return None
    current = now or datetime.now()
    return current + timedelta(seconds=seconds)
