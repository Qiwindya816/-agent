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

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(128))
    personalization_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    user_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    long_term_memory_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

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

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(255))
    current_trip_id: Mapped[str | None] = mapped_column(String(64))
    agent_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    user_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)

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

    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("chat_sessions.session_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    structured_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    token_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class Trip(Base, TimestampMixin):
    """表示 旅行 的数据库持久化实体。"""
    __tablename__ = "trips"
    __table_args__ = (Index("ix_trips_user_session_trip", "user_id", "session_id", "trip_id", unique=True),)

    trip_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("chat_sessions.session_id", ondelete="CASCADE"), nullable=False, index=True
    )
    destination: Mapped[str | None] = mapped_column(String(128))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), default="planning", nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    agent_state: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    user_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    structured_itinerary: Mapped[dict[str, Any] | None] = mapped_column(JSON)

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

    version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trip_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("trips.trip_id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    itinerary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    change_reason: Mapped[str | None] = mapped_column(Text)
    source_agent: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    trip: Mapped[Trip] = relationship(back_populates="versions")


class TripFeedback(Base):
    """表示 旅行、反馈 的数据库持久化实体。"""
    __tablename__ = "trip_feedback"
    __table_args__ = (Index("ix_trip_feedback_user_trip", "user_id", "trip_id"),)

    feedback_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trip_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("trips.trip_id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[str | None] = mapped_column(String(64))
    activity_id: Mapped[str | None] = mapped_column(String(128))
    feedback_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class MemoryItem(Base, TimestampMixin):
    """表示 记忆、记录 的数据库持久化实体。"""
    __tablename__ = "memory_items"
    __table_args__ = (Index("ix_memory_items_user_memory", "user_id", "memory_id", unique=True),)

    memory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    structured_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    scope: Mapped[str] = mapped_column(String(64), default="global", nullable=False)
    polarity: Mapped[str] = mapped_column(String(16), default="positive", nullable=False)
    importance: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="inferred", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    embedding: Mapped[Any | None] = mapped_column(
        Vector(1024).with_variant(JSON, "sqlite"),
        nullable=True,
    )
    embedding_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(back_populates="memories")
    evidence: Mapped[list["MemoryEvidence"]] = relationship(
        back_populates="memory", cascade="all, delete-orphan", passive_deletes=False
    )


class MemoryEvidence(Base):
    """表示 记忆、证据 的数据库持久化实体。"""
    __tablename__ = "memory_evidence"
    __table_args__ = (Index("ix_memory_evidence_user_memory", "user_id", "memory_id"),)

    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    memory_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("memory_items.memory_id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str | None] = mapped_column(String(64))
    message_id: Mapped[str | None] = mapped_column(String(64))
    trip_id: Mapped[str | None] = mapped_column(String(64))
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(64), default="explicit_statement", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    memory: Mapped[MemoryItem] = relationship(back_populates="evidence")


class RagSource(Base, TimestampMixin):
    """表示 RAG、知识来源 的数据库持久化实体。"""
    __tablename__ = "rag_sources"

    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(String(128))
    authorization_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    owner_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.user_id", ondelete="CASCADE"), index=True
    )
    documents: Mapped[list["RagDocument"]] = relationship(
        back_populates="source", cascade="all, delete-orphan", passive_deletes=False
    )


class RagDocument(Base, TimestampMixin):
    """表示 RAG、文档 的数据库持久化实体。"""
    __tablename__ = "rag_documents"
    __table_args__ = (Index("ix_rag_documents_owner_document", "owner_user_id", "document_id", unique=True),)

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("rag_sources.source_id", ondelete="CASCADE"), nullable=False, index=True
    )
    source: Mapped[RagSource] = relationship(back_populates="documents")
    owner_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.user_id", ondelete="CASCADE"), index=True
    )
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    raw_file_path: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
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

    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("rag_documents.document_id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_user_id: Mapped[str | None] = mapped_column(String(64), index=True)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String(32), nullable=False)
    city: Mapped[str | None] = mapped_column(String(64), index=True)
    district: Mapped[str | None] = mapped_column(String(64))
    poi_id: Mapped[str | None] = mapped_column(String(128), index=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    theme: Mapped[str | None] = mapped_column(String(64), index=True)
    travel_days: Mapped[int | None] = mapped_column(Integer)
    audience: Mapped[str | None] = mapped_column(String(64))
    season: Mapped[str | None] = mapped_column(String(32))
    price_level: Mapped[str | None] = mapped_column(String(32))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    document: Mapped[RagDocument] = relationship(back_populates="chunks")
    # PostgreSQL 使用 vector(1024)，SQLite 测试则使用可移植的 JSON 表示。
    embedding: Mapped[Any | None] = mapped_column(
        Vector(1024).with_variant(JSON, "sqlite"),
        nullable=True,
    )
    # PostgreSQL 将该字段定义为 GENERATED ALWAYS tsvector 列。SQLite 测试中保留
    # 可移植的 Text 声明，但 ORM 的查询和写入语句不得包含它；全文检索通过原生 SQL 访问。
    tsv: Mapped[Any | None] = mapped_column(Text, nullable=True, _omit_from_statements=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class RagIngestionJob(Base):
    """表示 RAG、导入、任务 的数据库持久化实体。"""
    __tablename__ = "rag_ingestion_jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    document_id: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SocialNote(Base):
    """封装 `SocialNote` 的核心数据与行为。"""

    __tablename__ = "social_notes"
    __table_args__ = (
        UniqueConstraint("platform", "external_note_id", name="uq_social_note_platform_external"),
        Index("ix_social_notes_city_platform", "city", "platform"),
    )

    social_note_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="xiaohongshu")
    external_note_id: Mapped[str] = mapped_column(String(128), nullable=False)
    document_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("rag_documents.document_id", ondelete="CASCADE"), nullable=False, unique=True
    )
    canonical_url: Mapped[str | None] = mapped_column(Text)
    author_hash: Mapped[str | None] = mapped_column(String(128))
    note_type: Mapped[str | None] = mapped_column(String(32))
    tags: Mapped[list[str] | None] = mapped_column(JSON)
    image_urls: Mapped[list[str] | None] = mapped_column(JSON)
    city: Mapped[str | None] = mapped_column(String(64), index=True)
    themes: Mapped[list[str] | None] = mapped_column(JSON)
    crawl_query: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class SocialMetricSnapshot(Base):
    """定义 `SocialMetricSnapshot` 使用的结构化数据。"""

    __tablename__ = "social_metric_snapshots"
    __table_args__ = (
        Index("ix_social_metric_note_captured", "social_note_id", "captured_at"),
    )

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    social_note_id: Mapped[str] = mapped_column(
        String(96), ForeignKey("social_notes.social_note_id", ondelete="CASCADE"), nullable=False, index=True
    )
    likes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    collects: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    comments: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    shares: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ToolCall(Base):
    """表示 工具、调用记录 的数据库持久化实体。"""
    __tablename__ = "tool_calls"
    __table_args__ = (Index("ix_tool_calls_user_session_trip", "user_id", "session_id", "trip_id"),)

    tool_call_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    session_id: Mapped[str | None] = mapped_column(String(64), index=True)
    trip_id: Mapped[str | None] = mapped_column(String(64), index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    arguments: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    retries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ProviderHealth(Base, TimestampMixin):
    """表示 服务提供方、健康状态 的数据库持久化实体。"""
    __tablename__ = "provider_health"

    provider_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    success_rate: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    average_latency: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    circuit_state: Mapped[str] = mapped_column(String(32), default="closed", nullable=False)
