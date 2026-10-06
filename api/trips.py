"""提供 FastAPI 接口、依赖注入与请求处理；本文件负责 `trips` 相关实现。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from uuid import uuid4

from api.dependencies import get_current_user, get_database
from db.engine import DatabaseEngine
from repositories.session_repository import SessionRepository
from repositories.trip_feedback_repository import TripFeedbackRepository
from repositories.trip_repository import PlanVersionRepository, TripRepository
from schemas.api import TripResponse, TripVersionResponse, UserContext
from schemas.itinerary import Itinerary

router = APIRouter(prefix="/trips", tags=["trips"])


def _trip_response(item) -> TripResponse:
    """将数据库旅行实体转换为 API 响应模型。"""
    return TripResponse(
        trip_id=item.trip_id,
        user_id=item.user_id,
        session_id=item.session_id,
        destination=item.destination,
        start_date=item.start_date.isoformat() if item.start_date else None,
        end_date=item.end_date.isoformat() if item.end_date else None,
        status=item.status,
        current_version=item.current_version,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("", response_model=list[TripResponse])
def list_trips(
    session_id: str,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> list[TripResponse]:
    """列出旅行列表并返回符合当前作用域的结果。"""
    with database.session() as session:
        try:
            items = TripRepository(session).list(user.user_id, session_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_trip_response(item) for item in items]


@router.get("/{trip_id}", response_model=TripResponse)
def get_trip(
    trip_id: str,
    session_id: str,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> TripResponse:
    """获取旅行并返回符合当前作用域的结果。"""
    with database.session() as session:
        item = TripRepository(session).get(user.user_id, session_id, trip_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Trip not found")
        return _trip_response(item)


@router.get("/{trip_id}/versions", response_model=list[TripVersionResponse])
def list_trip_versions(
    trip_id: str,
    session_id: str,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> list[TripVersionResponse]:
    """列出旅行、版本列表并返回符合当前作用域的结果。"""
    with database.session() as session:
        try:
            items = PlanVersionRepository(session).list(user.user_id, session_id, trip_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [
        TripVersionResponse(
            version_id=item.version_id,
            trip_id=item.trip_id,
            user_id=item.user_id,
            version_number=item.version_number,
            itinerary=item.itinerary,
            change_reason=item.change_reason,
            source_agent=item.source_agent,
            created_at=item.created_at,
        )
        for item in items
    ]


@router.post("/{trip_id}/map/enrich")
def enrich_trip_map(
    trip_id: str,
    session_id: str,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> dict:
    """为已有行程补全高德坐标，并保存为新的内部版本。"""
    from memory.memory_manager import load_agent_state, save_agent_state
    from services.itinerary_map_service import ItineraryMapService
    from services.itinerary_renderer import render_itinerary_markdown
    from tools.registry import build_default_registry

    with database.session() as session:
        trip = TripRepository(session).get(user.user_id, session_id, trip_id)
        if trip is None:
            raise HTTPException(status_code=404, detail="Trip not found")
        raw_itinerary = trip.structured_itinerary
    if not raw_itinerary:
        raise HTTPException(status_code=400, detail="当前行程没有可补全的结构化数据。")

    registry = build_default_registry()
    geocode_tool = registry.get("geocode")
    if geocode_tool is None:
        raise HTTPException(status_code=503, detail="高德地理编码 MCP 尚未配置。")

    state = load_agent_state(session_id, user.user_id)
    state.trip_id = trip_id
    itinerary = Itinerary.model_validate(raw_itinerary)
    enriched, result, resolved = ItineraryMapService().enrich(itinerary, geocode_tool, state)
    if not result.success:
        message = result.error.message if result.error else "高德地理编码调用失败。"
        raise HTTPException(status_code=502, detail=message)
    if resolved == 0:
        raise HTTPException(status_code=422, detail="没有找到可用于地图展示的景点坐标。")

    state.structured_itinerary = enriched
    state.current_itinerary = render_itinerary_markdown(enriched)
    save_agent_state(state)
    with database.session() as session:
        trip = TripRepository(session).require(user.user_id, session_id, trip_id)
        trip.structured_itinerary = enriched.model_dump(mode="json", exclude_none=True)
        version = PlanVersionRepository(session).create(
            user.user_id,
            session_id,
            trip_id,
            f"version_{uuid4().hex[:16]}",
            trip.structured_itinerary,
            change_reason="补全地图坐标",
            source_agent="map_enrichment",
        )
    return {
        "itinerary": enriched.model_dump(mode="json", exclude_none=True),
        "version_id": version.version_id,
        "version_number": version.version_number,
        "change_reason": "补全地图坐标",
        "resolved_activities": resolved,
    }


class ActivityEditRequest(BaseModel):
    """定义 活动、编辑 请求的数据结构。"""
    action: str
    activity_id: str | None = None
    day: int | None = 1
    start_time: str | None = None
    end_time: str | None = None
    name: str | None = None
    estimated_cost: float | None = Field(default=None, ge=0)
    notes: str | None = None
    activity: dict | None = None
    ordered_activity_ids: list[str] | None = None


class FeedbackRequest(BaseModel):
    """定义 反馈 请求的数据结构。"""
    feedback_type: str
    reason: str | None = None
    activity_id: str | None = None
    version_id: str | None = None


@router.post("/{trip_id}/activities/edit")
def edit_trip_activity(
    trip_id: str,
    session_id: str,
    request: ActivityEditRequest,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> dict:
    """对指定行程版本执行增删改排活动操作并保存新版本。"""
    from tools.itinerary_edit_tool import ItineraryEditTool

    with database.session() as session:
        trip = TripRepository(session).get(user.user_id, session_id, trip_id)
        if trip is None:
            raise HTTPException(status_code=404, detail="Trip not found")
        structured_itinerary = trip.structured_itinerary
    if not structured_itinerary:
        raise HTTPException(status_code=400, detail="Trip has no structured itinerary")

    class _State:
        """为行程编辑工具提供最小的可变状态适配器。"""
        pass

    state_object = _State()
    state_object.structured_itinerary = Itinerary.model_validate(structured_itinerary)
    result = ItineraryEditTool().run(
        {
            "state": state_object,
            "mcp_arguments": request.model_dump(exclude_none=True),
        }
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error.message if result.error else "Itinerary edit failed")
    edited = Itinerary.model_validate(result.data)
    change_reason = str(result.metadata.get("change_reason") or "局部修改行程")
    with database.session() as session:
        trip = TripRepository(session).require(user.user_id, session_id, trip_id)
        trip.structured_itinerary = edited.model_dump(mode="json", exclude_none=True)
        version = PlanVersionRepository(session).create(
            user.user_id,
            session_id,
            trip_id,
            f"version_{uuid4().hex[:16]}",
            trip.structured_itinerary,
            change_reason=change_reason,
            source_agent="frontend_edit",
        )
    return {
        "itinerary": edited.model_dump(mode="json", exclude_none=True),
        "version_id": version.version_id,
        "version_number": version.version_number,
        "change_reason": change_reason,
        "validation": result.metadata.get("validation", {}),
    }


@router.post("/{trip_id}/feedback", status_code=201)
def create_feedback(
    trip_id: str,
    session_id: str,
    request: FeedbackRequest,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> dict:
    """创建反馈，并保持相关状态或持久化数据一致。"""
    if request.feedback_type not in {"accept", "reject", "modify"}:
        raise HTTPException(status_code=422, detail="feedback_type must be accept, reject, or modify.")
    with database.session() as session:
        if TripRepository(session).get(user.user_id, session_id, trip_id) is None:
            raise HTTPException(status_code=404, detail="Trip not found")
        item = TripFeedbackRepository(session).create(
            user.user_id,
            trip_id,
            version_id=request.version_id,
            activity_id=request.activity_id,
            feedback_type=request.feedback_type,
            reason=request.reason,
        )
    return {"feedback_id": item.feedback_id, "feedback_type": item.feedback_type}
