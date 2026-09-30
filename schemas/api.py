"""Request and response schemas for the TravelMind FastAPI service."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UserContext(BaseModel):
    """Current user identity used for API isolation."""

    user_id: str


class SessionCreateRequest(BaseModel):
    title: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    title: str | None = None
    current_trip_id: str | None = None
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MessageCreateRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)


class MessageResponse(BaseModel):
    message_id: str
    session_id: str
    user_id: str
    role: str
    content: str
    created_at: datetime | None = None


class WorkflowResponse(BaseModel):
    session_id: str
    request_id: str | None
    response: str
    node_trace: list[str] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    execution_elapsed_seconds: float | None = None


class TripResponse(BaseModel):
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
    version_id: str
    trip_id: str
    user_id: str
    version_number: int
    itinerary: dict[str, Any]
    change_reason: str | None = None
    source_agent: str | None = None
    created_at: datetime | None = None


class MemoryResponse(BaseModel):
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
    statement: str


class MemorySettingsRequest(BaseModel):
    personalization_enabled: bool | None = None
    long_term_memory_enabled: bool | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "travelmind-api"
    database: bool = False
