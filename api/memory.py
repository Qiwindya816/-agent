"""Memory management endpoints with strict user isolation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_current_user, get_database
from db.engine import DatabaseEngine
from repositories.memory_repository import MemoryRepository
from repositories.user_repository import UserRepository
from schemas.api import MemoryResponse, MemorySettingsRequest, MemoryUpdateRequest, UserContext

router = APIRouter(prefix="/memory", tags=["memory"])


def _memory_response(item) -> MemoryResponse:
    return MemoryResponse(
        memory_id=item.memory_id,
        memory_type=item.memory_type,
        category=item.category,
        statement=item.statement,
        scope=item.scope,
        polarity=item.polarity,
        importance=item.importance,
        confidence=item.confidence,
        evidence_count=item.evidence_count,
        status=item.status,
        has_embedding=item.embedding is not None,
    )


@router.get("", response_model=list[MemoryResponse])
def list_memories(
    memory_type: str | None = None,
    scope: str | None = None,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> list[MemoryResponse]:
    with database.session() as session:
        items = MemoryRepository(session).list_items(user.user_id, memory_type=memory_type, scope=scope)
    return [_memory_response(item) for item in items]


@router.patch("/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: str,
    request: MemoryUpdateRequest,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> MemoryResponse:
    with database.session() as session:
        item = MemoryRepository(session).update_statement(user.user_id, memory_id, request.statement)
        if item is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        return _memory_response(item)


@router.delete("/{memory_id}")
def delete_memory(
    memory_id: str,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> dict[str, bool]:
    with database.session() as session:
        deleted = MemoryRepository(session).delete_item(user.user_id, memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"deleted": True}


@router.delete("")
def clear_memories(
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> dict[str, int]:
    with database.session() as session:
        deleted = MemoryRepository(session).clear_items(user.user_id)
    return {"deleted": deleted}


@router.post("/settings")
def update_settings(
    request: MemorySettingsRequest,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> dict[str, bool]:
    with database.session() as session:
        users = UserRepository(session)
        if users.get(user.user_id) is None:
            users.create(user.user_id)
        item = users.update_settings(
            user.user_id,
            personalization_enabled=request.personalization_enabled,
            long_term_memory_enabled=request.long_term_memory_enabled,
        )
    return {
        "personalization_enabled": item.personalization_enabled,
        "long_term_memory_enabled": item.long_term_memory_enabled,
    }
