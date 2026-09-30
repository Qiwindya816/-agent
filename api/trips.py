"""Trip and itinerary version endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import get_current_user, get_database
from db.engine import DatabaseEngine
from repositories.session_repository import SessionRepository
from repositories.trip_feedback_repository import TripFeedbackRepository
from repositories.trip_repository import PlanVersionRepository, TripRepository
from schemas.api import TripResponse, TripVersionResponse, UserContext

router = APIRouter(prefix="/trips", tags=["trips"])


def _trip_response(item) -> TripResponse:
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


class ActivityEditRequest(BaseModel):
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
    from tools.itinerary_edit_tool import ItineraryEditTool

    with database.session() as session:
        trip = TripRepository(session).get(user.user_id, session_id, trip_id)
        if trip is None:
            raise HTTPException(status_code=404, detail="Trip not found")
        state = trip.agent_state or {}
        structured_itinerary = trip.structured_itinerary
    if not structured_itinerary:
        raise HTTPException(status_code=400, detail="Trip has no structured itinerary")

    class _State:
        pass

    state_object = _State()
    state_object.structured_itinerary = structured_itinerary
    result = ItineraryEditTool().run(
        {
            "state": state_object,
            "mcp_arguments": request.model_dump(exclude_none=True),
        }
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error.message if result.error else "Itinerary edit failed")
    return result.data


@router.post("/{trip_id}/feedback", status_code=201)
def create_feedback(
    trip_id: str,
    session_id: str,
    request: FeedbackRequest,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> dict:
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
