"""Session and workflow endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session as OrmSession

from api.dependencies import get_current_user, get_database
from db.engine import DatabaseEngine
from db.models import ChatMessage
from multi_agent.workflow import MultiAgentTravelWorkflow
from repositories.session_repository import MessageRepository, SessionRepository
from repositories.user_repository import UserRepository
from schemas.api import (
    MessageCreateRequest,
    MessageResponse,
    SessionCreateRequest,
    SessionResponse,
    UserContext,
    WorkflowResponse,
)
from utils.ids import new_session_id

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _session_response(item) -> SessionResponse:
    return SessionResponse(
        session_id=item.session_id,
        user_id=item.user_id,
        title=item.title,
        current_trip_id=item.current_trip_id,
        status=item.status,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    request: SessionCreateRequest,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> SessionResponse:
    with database.session() as session:
        users = UserRepository(session)
        if users.get(user.user_id) is None:
            users.create(user.user_id)
        item = SessionRepository(session).create(user.user_id, new_session_id(), title=request.title)
    return _session_response(item)


@router.get("", response_model=list[SessionResponse])
def list_sessions(
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> list[SessionResponse]:
    with database.session() as session:
        items = SessionRepository(session).list(user.user_id)
    return [_session_response(item) for item in items]


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: str,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> SessionResponse:
    with database.session() as session:
        item = SessionRepository(session).get(user.user_id, session_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return _session_response(item)


@router.delete("/{session_id}")
def delete_session(
    session_id: str,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> dict[str, bool]:
    with database.session() as session:
        deleted = SessionRepository(session).delete(user.user_id, session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"deleted": True}


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
def list_messages(
    session_id: str,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> list[MessageResponse]:
    with database.session() as session:
        repository = MessageRepository(session)
        try:
            items = repository.list(user.user_id, session_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [
        MessageResponse(
            message_id=item.message_id,
            session_id=item.session_id,
            user_id=item.user_id,
            role=item.role,
            content=item.content,
            created_at=item.created_at,
        )
        for item in items
    ]


@router.post("/{session_id}/messages", response_model=WorkflowResponse)
def send_message(
    session_id: str,
    request: MessageCreateRequest,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> WorkflowResponse:
    with database.session() as session:
        if SessionRepository(session).get(user.user_id, session_id) is None:
            raise HTTPException(status_code=404, detail="Session not found")

    try:
        workflow = MultiAgentTravelWorkflow(user_id=user.user_id, session_id=session_id)
        result = workflow.run_with_state(request.message)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Workflow execution failed: {exc}") from exc

    return WorkflowResponse(
        session_id=session_id,
        request_id=result.get("request_id"),
        response=str(result.get("response", "")),
        node_trace=list(result.get("node_trace", [])),
        errors=list(result.get("errors", [])),
        execution_elapsed_seconds=result.get("execution_elapsed_seconds"),
    )
