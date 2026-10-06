"""提供 带用户隔离的数据访问；本文件负责 `trip_repository` 相关实现。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import Trip, TripPlanVersion


class TripRepository:
    """封装 `TripRepository` 对应实体的数据访问和作用域隔离。"""

    def __init__(self, session: Session) -> None:
        """初始化 TripRepository 及其运行依赖。"""
        self.session = session

    def create(
        self,
        user_id: str,
        session_id: str,
        trip_id: str,
        destination: str | None = None,
    ) -> Trip:
        """创建旅行，并保持相关状态或持久化数据一致。"""
        from repositories.session_repository import SessionRepository

        SessionRepository(self.session).require(user_id, session_id)
        trip = Trip(trip_id=trip_id, user_id=user_id, session_id=session_id, destination=destination)
        self.session.add(trip)
        self.session.flush()
        return trip

    def get(self, user_id: str, session_id: str, trip_id: str) -> Trip | None:
        """获取旅行并返回符合当前作用域的结果。"""
        trip = self.session.get(Trip, trip_id)
        if trip is None or trip.user_id != user_id or trip.session_id != session_id:
            return None
        return trip

    def require(self, user_id: str, session_id: str, trip_id: str) -> Trip:
        """返回用户会话中的指定旅行；不存在时抛出错误。"""
        trip = self.get(user_id, session_id, trip_id)
        if trip is None:
            raise LookupError(f"Trip not found for user/session: {user_id}/{session_id}/{trip_id}")
        return trip

    def list(self, user_id: str, session_id: str) -> list[Trip]:
        """列出旅行并返回符合当前作用域的结果。"""
        from repositories.session_repository import SessionRepository

        SessionRepository(self.session).require(user_id, session_id)
        statement = (
            select(Trip)
            .where(Trip.user_id == user_id, Trip.session_id == session_id)
            .order_by(Trip.created_at)
        )
        return list(self.session.scalars(statement))

    def delete(self, user_id: str, session_id: str, trip_id: str) -> bool:
        """删除旅行，并保持相关状态或持久化数据一致。"""
        trip = self.get(user_id, session_id, trip_id)
        if trip is None:
            return False
        self.session.delete(trip)
        self.session.flush()
        return True


class PlanVersionRepository:
    """封装 `PlanVersionRepository` 对应实体的数据访问和作用域隔离。"""

    def __init__(self, session: Session) -> None:
        """初始化 PlanVersionRepository 及其运行依赖。"""
        self.session = session

    def create(
        self,
        user_id: str,
        session_id: str,
        trip_id: str,
        version_id: str,
        itinerary: dict,
        change_reason: str | None = None,
        source_agent: str | None = None,
    ) -> TripPlanVersion:
        """创建计划、版本，并保持相关状态或持久化数据一致。"""
        trip = TripRepository(self.session).require(user_id, session_id, trip_id)
        next_version = trip.current_version + 1
        version = TripPlanVersion(
            version_id=version_id,
            trip_id=trip_id,
            user_id=user_id,
            version_number=next_version,
            itinerary=itinerary,
            change_reason=change_reason,
            source_agent=source_agent,
        )
        trip.current_version = next_version
        self.session.add(version)
        self.session.flush()
        return version

    def get(self, user_id: str, session_id: str, trip_id: str, version_id: str) -> TripPlanVersion | None:
        """获取计划、版本并返回符合当前作用域的结果。"""
        TripRepository(self.session).require(user_id, session_id, trip_id)
        version = self.session.get(TripPlanVersion, version_id)
        if version is None or version.user_id != user_id or version.trip_id != trip_id:
            return None
        return version

    def list(self, user_id: str, session_id: str, trip_id: str) -> list[TripPlanVersion]:
        """列出计划、版本并返回符合当前作用域的结果。"""
        TripRepository(self.session).require(user_id, session_id, trip_id)
        statement = (
            select(TripPlanVersion)
            .where(TripPlanVersion.user_id == user_id, TripPlanVersion.trip_id == trip_id)
            .order_by(TripPlanVersion.version_number)
        )
        return list(self.session.scalars(statement))


class ItineraryVersionService:
    """提供 `ItineraryVersionService` 对应领域能力的统一服务。"""

    def __init__(self, database) -> None:
        """初始化 ItineraryVersionService 及其运行依赖。"""
        self.database = database

    def save_version(
        self,
        user_id: str,
        session_id: str,
        trip_id: str,
        itinerary,
        *,
        change_reason: str,
        source_agent: str = "travelmind",
    ):
        """保存版本，并保持相关状态或持久化数据一致。"""
        from repositories.trip_repository import PlanVersionRepository

        from utils.ids import new_request_id
        with self.database.session() as session:
            repository = PlanVersionRepository(session)
            return repository.create(
                user_id,
                session_id,
                trip_id,
                f"version_{new_request_id().removeprefix('req_')}",
                itinerary.model_dump(mode="json", exclude_none=True),
                change_reason=change_reason,
                source_agent=source_agent,
            )
