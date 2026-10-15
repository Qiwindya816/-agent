"""提供 数据库模型、连接与初始化；本文件负责 `models` 相关实现。"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from db.base import Base, TimestampMixin, utc_now


class User(Base, TimestampMixin):
    """表示 用户 的数据库持久化实体。"""
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 用户 ID
    display_name: Mapped[str | None] = mapped_column(String(128))  # 显示名
    personalization_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # 是否启用个性化
    user_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # 长期画像快照
    long_term_memory_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # 是否启用长期记忆

    sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=False
    )
    trips: Mapped[list["Trip"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=False
    )
    memories: Mapped[list["MemoryItem"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=False
    )


class ChatSession(Base, TimestampMixin):
    """表示 聊天、会话 的数据库持久化实体。"""
    __tablename__ = "chat_sessions"
    __table_args__ = (Index("ix_chat_sessions_user_session", "user_id", "session_id", unique=True),)

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 会话 ID
    user_id: Mapped[str] = mapped_column(  # 用户 ID
        String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255))  # 标题
    current_trip_id: Mapped[str | None] = mapped_column(String(64))  # 当前行程 ID
    agent_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # Agent 状态快照
    user_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # 用户画像快照
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)  # 状态

    user: Mapped[User] = relationship(back_populates="sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=False
    )


class ChatMessage(Base):
    """表示 聊天、消息 的数据库持久化实体。"""
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_user_session_message", "user_id", "session_id", "message_id", unique=True),
    )

    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 消息 ID
    session_id: Mapped[str] = mapped_column(  # 会话 ID
        String(64), ForeignKey("chat_sessions.session_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(  # 用户 ID
        String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # 角色
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 文本
    structured_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # 结构化负载
    token_count: Mapped[int | None] = mapped_column(Integer)  # Token 数
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)  # 创建时间

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class Trip(Base, TimestampMixin):
    """表示 旅行 的数据库持久化实体。"""
    __tablename__ = "trips"
    __table_args__ = (Index("ix_trips_user_session_trip", "user_id", "session_id", "trip_id", unique=True),)

    trip_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 行程 ID
    user_id: Mapped[str] = mapped_column(  # 用户 ID
        String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(  # 会话 ID
        String(64), ForeignKey("chat_sessions.session_id", ondelete="CASCADE"), nullable=False, index=True
    )
    destination: Mapped[str | None] = mapped_column(String(128))  # 目的地
    start_date: Mapped[date | None] = mapped_column(Date)  # 开始日期
    end_date: Mapped[date | None] = mapped_column(Date)  # 结束日期
    status: Mapped[str] = mapped_column(String(32), default="planning", nullable=False)  # 状态
    current_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 当前版本号
    agent_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # Agent 状态
    user_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # 用户画像
    structured_itinerary: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # 结构化行程

    user: Mapped[User] = relationship(back_populates="trips")
    versions: Mapped[list["TripPlanVersion"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan", passive_deletes=False
    )


class TripPlanVersion(Base):
    """表示 旅行、计划、版本 的数据库持久化实体。"""
    __tablename__ = "trip_plan_versions"
    __table_args__ = (
        UniqueConstraint("trip_id", "version_number", name="uq_trip_plan_version"),
        Index("ix_trip_plan_versions_user_trip_version", "user_id", "trip_id", "version_id", unique=True),
    )

    version_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 版本 ID
    trip_id: Mapped[str] = mapped_column(  # 行程 ID
        String(64), ForeignKey("trips.trip_id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(  # 用户 ID
        String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 版本序号
    itinerary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)  # 结构化行程 JSON
    change_reason: Mapped[str | None] = mapped_column(Text)  # 修改原因
    source_agent: Mapped[str | None] = mapped_column(String(128))  # 来源 Agent
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)  # 创建时间

    trip: Mapped[Trip] = relationship(back_populates="versions")


class TripFeedback(Base):
    """表示 旅行、反馈 的数据库持久化实体。"""
    __tablename__ = "trip_feedback"
    __table_args__ = (Index("ix_trip_feedback_user_trip", "user_id", "trip_id"),)

    feedback_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 反馈 ID
    trip_id: Mapped[str] = mapped_column(  # 行程 ID
        String(64), ForeignKey("trips.trip_id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(  # 用户 ID
        String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[str | None] = mapped_column(String(64))  # 版本 ID
    activity_id: Mapped[str | None] = mapped_column(String(128))  # 活动 ID
    feedback_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 反馈类型
    reason: Mapped[str | None] = mapped_column(Text)  # 原因
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)  # 创建时间


class MemoryItem(Base, TimestampMixin):
    """表示 记忆、记录 的数据库持久化实体。"""
    __tablename__ = "memory_items"
    __table_args__ = (Index("ix_memory_items_user_memory", "user_id", "memory_id", unique=True),)

    memory_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 记忆 ID
    user_id: Mapped[str] = mapped_column(  # 用户 ID
        String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 类型
    category: Mapped[str] = mapped_column(String(64), nullable=False)  # 分类
    statement: Mapped[str] = mapped_column(Text, nullable=False)  # 陈述
    structured_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # 结构化值
    scope: Mapped[str] = mapped_column(String(64), default="global", nullable=False)  # 作用域
    polarity: Mapped[str] = mapped_column(String(16), default="positive", nullable=False)  # 倾向
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)  # 重要度
    confidence: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)  # 置信度
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 证据数
    source_type: Mapped[str] = mapped_column(String(32), default="inferred", nullable=False)  # 来源类型
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)  # 状态
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)  # 首次观察时间
    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 最近确认时间
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 过期时间
    embedding: Mapped[Any | None] = mapped_column(  # 向量
        Vector(1024).with_variant(JSON, "sqlite"),
        nullable=True,
    )
    embedding_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # 向量原文

    user: Mapped[User] = relationship(back_populates="memories")
    evidence: Mapped[list["MemoryEvidence"]] = relationship(
        back_populates="memory", cascade="all, delete-orphan", passive_deletes=False
    )


class MemoryEvidence(Base):
    """表示 记忆、证据 的数据库持久化实体。"""
    __tablename__ = "memory_evidence"
    __table_args__ = (Index("ix_memory_evidence_user_memory", "user_id", "memory_id"),)

    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 证据 ID
    memory_id: Mapped[str] = mapped_column(  # 记忆 ID
        String(64), ForeignKey("memory_items.memory_id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(  # 用户 ID
        String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str | None] = mapped_column(String(64))  # 会话 ID
    message_id: Mapped[str | None] = mapped_column(String(64))  # 消息 ID
    trip_id: Mapped[str | None] = mapped_column(String(64))  # 行程 ID
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)  # 证据文本
    evidence_type: Mapped[str] = mapped_column(String(64), default="explicit_statement", nullable=False)  # 证据类型
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)  # 置信度
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)  # 观察时间

    memory: Mapped[MemoryItem] = relationship(back_populates="evidence")


class RagSource(Base, TimestampMixin):
    """表示 RAG、知识来源 的数据库持久化实体。"""
    __tablename__ = "rag_sources"

    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 来源 ID
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 来源类型
    name: Mapped[str] = mapped_column(String(255), nullable=False)  # 名称
    url: Mapped[str | None] = mapped_column(Text)  # 链接
    license: Mapped[str | None] = mapped_column(String(128))  # 授权
    authorization_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)  # 授权状态
    owner_user_id: Mapped[str | None] = mapped_column(  # 所属用户
        String(64), ForeignKey("users.user_id", ondelete="CASCADE"), index=True
    )
    documents: Mapped[list["RagDocument"]] = relationship(
        back_populates="source", cascade="all, delete-orphan", passive_deletes=False
    )


class RagDocument(Base, TimestampMixin):
    """表示 RAG、文档 的数据库持久化实体。"""
    __tablename__ = "rag_documents"
    __table_args__ = (Index("ix_rag_documents_owner_document", "owner_user_id", "document_id", unique=True),)

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 文档 ID
    source_id: Mapped[str] = mapped_column(  # 来源 ID
        String(64), ForeignKey("rag_sources.source_id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[RagSource] = relationship(back_populates="documents")
    owner_user_id: Mapped[str | None] = mapped_column(  # 所属用户
        String(64), ForeignKey("users.user_id", ondelete="CASCADE"), index=True
    )
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)  # 内容哈希
    raw_file_path: Mapped[str | None] = mapped_column(Text)  # 原始文件路径
    title: Mapped[str] = mapped_column(String(255), nullable=False)  # 标题
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 发布时间
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)  # 状态
    chunks: Mapped[list["RagChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=False
    )


class RagChunk(Base):
    """表示 RAG、切片 的数据库持久化实体。"""
    __mapper_args__ = {"eager_defaults": False}

    @classmethod
    def __declare_last__(cls) -> None:
        """将 PostgreSQL 生成列标记为 ORM 只读字段。"""
        cls.__table__.c.tsv._create_rule = lambda: None
        cls.__table__.c.tsv.server_onupdate = None
    __tablename__ = "rag_chunks"
    __table_args__ = (Index("ix_rag_chunks_owner_chunk", "owner_user_id", "chunk_id", unique=True),)

    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # Chunk ID
    document_id: Mapped[str] = mapped_column(  # 文档 ID
        String(64), ForeignKey("rag_documents.document_id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_user_id: Mapped[str | None] = mapped_column(String(64), index=True)  # 所属用户
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)  # 文本
    chunk_type: Mapped[str] = mapped_column(String(32), nullable=False)  # 类型
    city: Mapped[str | None] = mapped_column(String(64), index=True)  # 城市
    district: Mapped[str | None] = mapped_column(String(64))  # 区域
    poi_id: Mapped[str | None] = mapped_column(String(128), index=True)  # POI ID
    latitude: Mapped[float | None] = mapped_column(Float)  # 纬度
    longitude: Mapped[float | None] = mapped_column(Float)  # 经度
    theme: Mapped[str | None] = mapped_column(String(64), index=True)  # 主题
    travel_days: Mapped[int | None] = mapped_column(Integer)  # 旅行天数
    audience: Mapped[str | None] = mapped_column(String(64))  # 人群
    season: Mapped[str | None] = mapped_column(String(32))  # 季节
    price_level: Mapped[str | None] = mapped_column(String(32))  # 价格档位
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # 元数据
    document: Mapped[RagDocument] = relationship(back_populates="chunks")
    # PostgreSQL 使用 vector(1024)，SQLite 测试则使用可移植的 JSON 表示。
    embedding: Mapped[Any | None] = mapped_column(  # 向量
        Vector(1024).with_variant(JSON, "sqlite"),
        nullable=True,
    )
    # PostgreSQL 将该字段定义为 GENERATED ALWAYS tsvector 列。SQLite 测试中保留
    # 可移植的 Text 声明，但 ORM 的查询和写入语句不得包含它；全文检索通过原生 SQL 访问。
    tsv: Mapped[Any | None] = mapped_column(Text, nullable=True, _omit_from_statements=True)  # 全文检索向量
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)  # 创建时间


class RagIngestionJob(Base):
    """表示 RAG、导入、任务 的数据库持久化实体。"""
    __tablename__ = "rag_ingestion_jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 任务 ID
    source_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # 来源 ID
    document_id: Mapped[str | None] = mapped_column(String(64), index=True)  # 文档 ID
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)  # 状态
    error_message: Mapped[str | None] = mapped_column(Text)  # 错误信息
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 开始时间
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 结束时间


class SocialNote(Base):
    """封装 `SocialNote` 的核心数据与行为。"""

    __tablename__ = "social_notes"
    __table_args__ = (
        UniqueConstraint("platform", "external_note_id", name="uq_social_note_platform_external"),
        Index("ix_social_notes_city_platform", "city", "platform"),
    )

    social_note_id: Mapped[str] = mapped_column(String(96), primary_key=True)  # 笔记 ID
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="xiaohongshu")  # 平台
    external_note_id: Mapped[str] = mapped_column(String(128), nullable=False)  # 外部笔记 ID
    document_id: Mapped[str] = mapped_column(  # 文档 ID
        String(64), ForeignKey("rag_documents.document_id", ondelete="CASCADE"), nullable=False, unique=True
    )
    canonical_url: Mapped[str | None] = mapped_column(Text)  # 规范链接
    author_hash: Mapped[str | None] = mapped_column(String(128))  # 作者哈希
    note_type: Mapped[str | None] = mapped_column(String(32))  # 笔记类型
    tags: Mapped[list[str] | None] = mapped_column(JSON)  # 标签
    image_urls: Mapped[list[str] | None] = mapped_column(JSON)  # 图片
    city: Mapped[str | None] = mapped_column(String(64), index=True)  # 城市
    themes: Mapped[list[str] | None] = mapped_column(JSON)  # 主题
    crawl_query: Mapped[str | None] = mapped_column(String(255))  # 抓取查询
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 发布时间
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)  # 抓取时间


class SocialMetricSnapshot(Base):
    """定义 `SocialMetricSnapshot` 使用的结构化数据。"""

    __tablename__ = "social_metric_snapshots"
    __table_args__ = (
        Index("ix_social_metric_note_captured", "social_note_id", "captured_at"),
    )

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 快照 ID
    social_note_id: Mapped[str] = mapped_column(  # 笔记 ID
        String(96), ForeignKey("social_notes.social_note_id", ondelete="CASCADE"), nullable=False, index=True
    )
    likes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)  # 点赞
    collects: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)  # 收藏
    comments: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)  # 评论
    shares: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)  # 分享
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)  # 采集时间


class ToolCall(Base):
    """表示 工具、调用记录 的数据库持久化实体。"""
    __tablename__ = "tool_calls"
    __table_args__ = (Index("ix_tool_calls_user_session_trip", "user_id", "session_id", "trip_id"),)

    tool_call_id: Mapped[str] = mapped_column(String(64), primary_key=True)  # 调用 ID
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # 用户 ID
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)  # 会话 ID
    trip_id: Mapped[str | None] = mapped_column(String(64), index=True)  # 行程 ID
    provider: Mapped[str] = mapped_column(String(64), nullable=False)  # 提供方
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)  # 工具名
    arguments: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # 参数
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)  # 结果
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # 状态
    error_code: Mapped[str | None] = mapped_column(String(128))  # 错误码
    latency_ms: Mapped[int | None] = mapped_column(Integer)  # 耗时毫秒
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 重试次数
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # 缓存命中
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)  # 创建时间


class ProviderHealth(Base, TimestampMixin):
    """表示 服务提供方、健康状态 的数据库持久化实体。"""
    __tablename__ = "provider_health"

    provider_name: Mapped[str] = mapped_column(String(64), primary_key=True)  # 提供方
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # 状态
    success_rate: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)  # 成功率
    average_latency: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)  # 平均延迟
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 最近成功时间
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 最近失败时间
    circuit_state: Mapped[str] = mapped_column(String(32), default="closed", nullable=False)  # 熔断状态
