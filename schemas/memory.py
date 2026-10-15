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

    user_id: str  # 用户 ID
    memory_type: MemoryType  # 记忆类型
    category: str  # 分类
    statement: str  # 自然语言陈述
    structured_value: dict[str, Any] | None = None  # 结构化值
    scope: str = "global"  # 作用域
    polarity: Literal["positive", "negative", "neutral"] = "positive"  # 倾向
    importance: float = Field(default=0.5, ge=0, le=1)  # 重要度
    confidence: float = Field(default=0.7, ge=0, le=1)  # 置信度
    evidence_text: str  # 证据原文
    evidence_type: EvidenceType = "explicit_statement"  # 证据类型
    session_id: str | None = None  # 来源会话
    message_id: str | None = None  # 来源消息
    trip_id: str | None = None  # 来源行程


class RetrievedMemory(BaseModel):
    """承载 `RetrievedMemory` 对应的结构化结果及元数据。"""

    memory_id: str  # 记忆 ID
    user_id: str  # 用户 ID
    memory_type: MemoryType  # 类型
    category: str  # 分类
    statement: str  # 陈述
    structured_value: dict[str, Any] | None = None  # 结构化值
    scope: str  # 作用域
    polarity: str  # 倾向
    importance: float  # 重要度
    confidence: float  # 置信度
    evidence_count: int  # 证据数
    status: str  # 状态
    first_observed_at: datetime | None = None  # 首次观察时间
    last_confirmed_at: datetime | None = None  # 最近确认时间
    expires_at: datetime | None = None  # 过期时间
    similarity: float = 0.0  # 相似度


class MemoryDecision(BaseModel):
    """承载 `MemoryDecision` 对应的结构化结果及元数据。"""

    memory: RetrievedMemory  # 命中的记忆
    priority: float  # 注入优先级
    reason: str  # 选择原因
    suppressed_by: str | None = None  # 被哪条记忆压制


class MemoryWriteDecision(BaseModel):
    """承载 `MemoryWriteDecision` 对应的结构化结果及元数据。"""

    action: Literal["create", "merge", "reject", "defer"]  # 写入决策：create/merge/reject/defer
    memory_id: str | None = None  # 已有记忆 ID
    reason: str  # 决策原因
    required_evidence_count: int = 2  # 所需最少证据数
