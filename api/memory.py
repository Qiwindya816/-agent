"""提供 FastAPI 接口、依赖注入与请求处理；本文件负责 `memory` 相关实现。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_current_user, get_database
from db.engine import DatabaseEngine
from repositories.memory_repository import MemoryRepository
from repositories.user_repository import UserRepository
from schemas.api import MemoryResponse, MemorySettingsRequest, MemoryUpdateRequest, UserContext

router = APIRouter(prefix="/memory", tags=["memory"])


def _memory_response(item) -> MemoryResponse:
    """将数据库记忆实体转换为 API 响应模型。"""
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
    """列出记忆列表并返回符合当前作用域的结果。"""
    with database.session() as session:
        items = MemoryRepository(session).list_items(user.user_id, memory_type=memory_type, scope=scope)
    return [_memory_response(item) for item in items]


@router.get("/settings")
def get_settings(
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> dict[str, bool]:
    """获取设置并返回符合当前作用域的结果。"""
    with database.session() as session:
        users = UserRepository(session)
        item = users.get(user.user_id)
        if item is None:
            item = users.create(user.user_id)
    return {
        "personalization_enabled": item.personalization_enabled,
        "long_term_memory_enabled": item.long_term_memory_enabled,
    }


@router.patch("/{memory_id}", response_model=MemoryResponse)
def update_memory(
    memory_id: str,
    request: MemoryUpdateRequest,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> MemoryResponse:
    """更新记忆，并保持相关状态或持久化数据一致。"""
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
    """删除记忆，并保持相关状态或持久化数据一致。"""
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
    """清空记忆列表，并保持相关状态或持久化数据一致。"""
    with database.session() as session:
        deleted = MemoryRepository(session).clear_items(user.user_id)
    return {"deleted": deleted}


@router.post("/settings")
def update_settings(
    request: MemorySettingsRequest,
    user: UserContext = Depends(get_current_user),
    database: DatabaseEngine = Depends(get_database),
) -> dict[str, bool]:
    """更新设置，并保持相关状态或持久化数据一致。"""
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
