"""提供 Pydantic 结构化数据模型；本文件负责 `api` 相关实现。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UserContext(BaseModel):
    """定义 `UserContext` 使用的结构化数据。"""

    user_id: str  # 当前请求用户 ID


class SessionCreateRequest(BaseModel):
    """定义创建聊天会话时允许提交的字段。"""
    title: str | None = None  # 会话标题


class SessionResponse(BaseModel):
    """定义 会话 响应的数据结构。"""
    session_id: str  # 会话 ID
    user_id: str  # 用户 ID
    title: str | None = None  # 会话标题
    current_trip_id: str | None = None  # 当前行程 ID
    status: str  # 会话状态
    created_at: datetime | None = None  # 创建时间
    updated_at: datetime | None = None  # 更新时间


class MessageCreateRequest(BaseModel):
    """定义发送一条用户消息时的请求结构。"""
    message: str = Field(min_length=1, max_length=8000)  # 用户输入内容


class MessageResponse(BaseModel):
    """定义 消息 响应的数据结构。"""
    message_id: str  # 消息 ID
    session_id: str  # 会话 ID
    user_id: str  # 用户 ID
    role: str  # 消息角色
    content: str  # 消息内容
    created_at: datetime | None = None  # 创建时间


class WorkflowResponse(BaseModel):
    """定义 工作流 响应的数据结构。"""
    session_id: str  # 会话 ID
    request_id: str | None  # 请求 ID
    response: str  # 模型/系统回复
    node_trace: list[str] = Field(default_factory=list)  # 节点执行轨迹
    errors: list[dict[str, Any]] = Field(default_factory=list)  # 错误列表
    execution_elapsed_seconds: float | None = None  # 执行耗时秒数


class TripResponse(BaseModel):
    """定义 旅行 响应的数据结构。"""
    trip_id: str  # 行程 ID
    user_id: str  # 用户 ID
    session_id: str  # 会话 ID
    destination: str | None = None  # 目的地
    start_date: str | None = None  # 开始日期
    end_date: str | None = None  # 结束日期
    status: str  # 状态
    current_version: int  # 当前版本号
    created_at: datetime | None = None  # 创建时间
    updated_at: datetime | None = None  # 更新时间


class TripVersionResponse(BaseModel):
    """定义 旅行、版本 响应的数据结构。"""
    version_id: str  # 版本 ID
    trip_id: str  # 行程 ID
    user_id: str  # 用户 ID
    version_number: int  # 版本序号
    itinerary: dict[str, Any]  # 结构化行程
    change_reason: str | None = None  # 修改原因
    source_agent: str | None = None  # 产生版本的 Agent/工具
    created_at: datetime | None = None  # 创建时间


class MemoryResponse(BaseModel):
    """定义 记忆 响应的数据结构。"""
    memory_id: str  # 记忆 ID
    memory_type: str  # 记忆类型
    category: str  # 分类
    statement: str  # 记忆陈述
    scope: str  # 作用域
    polarity: str  # 情感/倾向
    importance: float  # 重要度
    confidence: float  # 置信度
    evidence_count: int  # 证据数量
    status: str  # 状态
    has_embedding: bool = False  # 是否已有向量


class MemoryUpdateRequest(BaseModel):
    """定义用户修改长期记忆陈述时的请求结构。"""
    statement: str  # 更新后的记忆陈述


class MemorySettingsRequest(BaseModel):
    """定义 记忆、设置 请求的数据结构。"""
    personalization_enabled: bool | None = None  # 是否启用个性化
    long_term_memory_enabled: bool | None = None  # 是否启用长期记忆


class HealthResponse(BaseModel):
    """定义 健康状态 响应的数据结构。"""
    status: str = "ok"  # 服务状态
    service: str = "travelmind-api"  # 服务名
    database: bool = False  # 数据库是否可用
