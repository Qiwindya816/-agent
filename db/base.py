"""提供 数据库模型、连接与初始化；本文件负责 `base` 相关实现。"""

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    """返回带时区信息的 UTC 当前时间。"""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """封装 `Base` 的核心数据与行为。"""


class TimestampMixin:
    """封装 `TimestampMixin` 的核心数据与行为。"""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
