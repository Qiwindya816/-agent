"""提供 FastAPI 接口、依赖注入与请求处理；本文件负责 `sessions` 相关实现。"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
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


def _execute_workflow(user_id: str, session_id: str, message: str) -> dict:
    """为指定用户和会话执行一次完整的多 Agent 工作流。"""
    workflow = MultiAgentTravelWorkflow(user_id=user_id, session_id=session_id)
    return workflow.run_with_state(message)


def _session_response(item) -> SessionResponse:
    """将数据库会话实体转换为 API 响应模型。"""
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
    """创建会话，并保持相关状态或持久化数据一致。"""
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
    """列出会话列表并返回符合当前作用域的结果。"""
    with database.session() as session:
        items = SessionRepository(session).list(user.user_id)
    return [_session_response(item) for item in items]


@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: str,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> SessionResponse:
    """获取会话并返回符合当前作用域的结果。"""
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
    """删除会话，并保持相关状态或持久化数据一致。"""
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
    """列出消息列表并返回符合当前作用域的结果。"""
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
    """执行用户消息并返回完整工作流响应。"""
    with database.session() as session:
        if SessionRepository(session).get(user.user_id, session_id) is None:
            raise HTTPException(status_code=404, detail="Session not found")

    try:
        result = _execute_workflow(user.user_id, session_id, request.message)
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


@router.post("/{session_id}/messages/stream")
async def stream_message(
    session_id: str,
    request: MessageCreateRequest,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> StreamingResponse:
    """以流式方式处理消息的完整业务流程并返回执行结果。"""
    with database.session() as session:
        if SessionRepository(session).get(user.user_id, session_id) is None:
            raise HTTPException(status_code=404, detail="Session not found")

    def event(name: str, payload: dict) -> str:
        """将事件名称和载荷编码为 SSE 消息块。"""
        return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"

    async def generate():
        """依次产出工作流状态、结果或错误 SSE 事件。"""
        yield event("status", {"stage": "thinking", "message": "TravelMind 正在理解你的需求"})
        try:
            result = await asyncio.to_thread(
                _execute_workflow,
                user.user_id,
                session_id,
                request.message,
            )
            payload = WorkflowResponse(
                session_id=session_id,
                request_id=result.get("request_id"),
                response=str(result.get("response", "")),
                node_trace=list(result.get("node_trace", [])),
                errors=list(result.get("errors", [])),
                execution_elapsed_seconds=result.get("execution_elapsed_seconds"),
            ).model_dump(mode="json")
            yield event("message", payload)
            yield event("done", {"ok": True})
        except Exception as exc:
            yield event("error", {"code": "workflow_failed", "message": str(exc)})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
