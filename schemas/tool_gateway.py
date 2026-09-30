"""Tool Gateway descriptors and metadata models."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field


class ToolDescriptor(BaseModel):
    """Stable description of a local tool exposed by the gateway."""

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
    """Provider identity and circuit state."""

    name: str
    status: str = "unknown"
    circuit_state: str = "closed"
    success_rate: float = 1.0
    average_latency: float = 0.0
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None


class GatewayCallContext(BaseModel):
    """User/session/trip ownership for an audited tool call."""

    user_id: str
    session_id: str | None = None
    trip_id: str | None = None
    request_id: str | None = None


class ToolCallSnapshot(BaseModel):
    """Serializable audit snapshot for a gateway call."""

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
    """Return a metadata expiry timestamp, or None for durable facts."""
    if seconds is None:
        return None
    current = now or datetime.now()
    return current + timedelta(seconds=seconds)
