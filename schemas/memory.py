"""提供 Pydantic 结构化数据模型；本文件负责 `memory` 相关实现。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


MemoryType = Literal["semantic", "episodic", "procedural", "explicit"]
EvidenceType = Literal[
    "explicit_statement",
    "inferred_behavior",
    "accepted_action",
    "rejected_action",
    "modified_action",
    "workflow_pattern",
]


class MemoryCandidate(BaseModel):
    """封装 `MemoryCandidate` 的核心数据与行为。"""

    user_id: str
    memory_type: MemoryType
    category: str
    statement: str
    structured_value: dict[str, Any] | None = None
    scope: str = "global"
    polarity: Literal["positive", "negative", "neutral"] = "positive"
    importance: float = Field(default=0.5, ge=0, le=1)
    confidence: float = Field(default=0.7, ge=0, le=1)
    evidence_text: str
    evidence_type: EvidenceType = "explicit_statement"
    session_id: str | None = None
    message_id: str | None = None
    trip_id: str | None = None


class RetrievedMemory(BaseModel):
    """承载 `RetrievedMemory` 对应的结构化结果及元数据。"""

    memory_id: str
    user_id: str
    memory_type: MemoryType
    category: str
    statement: str
    structured_value: dict[str, Any] | None = None
    scope: str
    polarity: str
    importance: float
    confidence: float
    evidence_count: int
    status: str
    first_observed_at: datetime | None = None
    last_confirmed_at: datetime | None = None
    expires_at: datetime | None = None
    similarity: float = 0.0


class MemoryDecision(BaseModel):
    """承载 `MemoryDecision` 对应的结构化结果及元数据。"""

    memory: RetrievedMemory
    priority: float
    reason: str
    suppressed_by: str | None = None


class MemoryWriteDecision(BaseModel):
    """承载 `MemoryWriteDecision` 对应的结构化结果及元数据。"""

    action: Literal["create", "merge", "reject", "defer"]
    memory_id: str | None = None
    reason: str
    required_evidence_count: int = 2
