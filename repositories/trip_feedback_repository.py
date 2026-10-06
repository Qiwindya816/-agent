"""提供 带用户隔离的数据访问；本文件负责 `trip_feedback_repository` 相关实现。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import uuid4

from db.models import TripFeedback


class TripFeedbackRepository:
    """封装 `TripFeedbackRepository` 对应实体的数据访问和作用域隔离。"""

    def __init__(self, session: Session) -> None:
        """初始化 TripFeedbackRepository 及其运行依赖。"""
        self.session = session

    def create(
        self,
        user_id: str,
        trip_id: str,
        *,
        version_id: str | None = None,
        activity_id: str | None = None,
        feedback_type: str,
        reason: str | None = None,
    ) -> TripFeedback:
        """创建旅行、反馈，并保持相关状态或持久化数据一致。"""
        if feedback_type not in {"accept", "reject", "modify"}:
            raise ValueError("feedback_type must be accept, reject, or modify.")
        feedback = TripFeedback(
            feedback_id=f"feedback_{uuid4().hex[:16]}",
            trip_id=trip_id,
            user_id=user_id,
            version_id=version_id,
            activity_id=activity_id,
            feedback_type=feedback_type,
            reason=reason,
        )
        self.session.add(feedback)
        self.session.flush()
        return feedback

    def list_for_trip(self, user_id: str, trip_id: str) -> list[TripFeedback]:
        """列出旅行并返回符合当前作用域的结果。"""
        statement = (
            select(TripFeedback)
            .where(TripFeedback.user_id == user_id, TripFeedback.trip_id == trip_id)
            .order_by(TripFeedback.created_at)
        )
        return list(self.session.scalars(statement))
