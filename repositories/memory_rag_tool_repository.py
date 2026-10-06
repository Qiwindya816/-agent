"""提供 带用户隔离的数据访问；本文件负责 `memory_rag_tool_repository` 相关实现。"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import MemoryEvidence, MemoryItem, RagChunk, ToolCall


class MemoryRepository:
    """封装 `MemoryRepository` 对应实体的数据访问和作用域隔离。"""

    def __init__(self, session: Session) -> None:
        """初始化 MemoryRepository 及其运行依赖。"""
        self.session = session

    def create(
        self,
        user_id: str,
        memory_id: str,
        memory_type: str,
        category: str,
        statement: str,
        structured_value: dict | None = None,
        scope: str = "global",
    ) -> MemoryItem:
        """创建记忆，并保持相关状态或持久化数据一致。"""
        from repositories.user_repository import UserRepository

        UserRepository(self.session).require(user_id)
        memory = MemoryItem(
            memory_id=memory_id,
            user_id=user_id,
            memory_type=memory_type,
            category=category,
            statement=statement,
            structured_value=structured_value,
            scope=scope,
        )
        self.session.add(memory)
        self.session.flush()
        return memory

    def get(self, user_id: str, memory_id: str) -> MemoryItem | None:
        """获取记忆并返回符合当前作用域的结果。"""
        memory = self.session.get(MemoryItem, memory_id)
        if memory is None or memory.user_id != user_id:
            return None
        return memory

    def list(self, user_id: str) -> list[MemoryItem]:
        """列出记忆并返回符合当前作用域的结果。"""
        statement = select(MemoryItem).where(MemoryItem.user_id == user_id).order_by(MemoryItem.created_at)
        return list(self.session.scalars(statement))

    def add_evidence(
        self,
        user_id: str,
        memory_id: str,
        evidence_id: str,
        evidence_text: str,
        session_id: str | None = None,
        message_id: str | None = None,
        trip_id: str | None = None,
    ) -> MemoryEvidence:
        """添加证据，并保持相关状态或持久化数据一致。"""
        memory = self.require(user_id, memory_id)
        evidence = MemoryEvidence(
            evidence_id=evidence_id,
            memory_id=memory.memory_id,
            user_id=user_id,
            session_id=session_id,
            message_id=message_id,
            trip_id=trip_id,
            evidence_text=evidence_text,
        )
        memory.evidence_count += 1
        memory.last_confirmed_at = func.now()
        self.session.add(evidence)
        self.session.flush()
        return evidence

    def require(self, user_id: str, memory_id: str) -> MemoryItem:
        """返回指定用户的记忆；不存在时抛出错误。"""
        memory = self.get(user_id, memory_id)
        if memory is None:
            raise LookupError(f"Memory not found for user {user_id}: {memory_id}")
        return memory

    def delete(self, user_id: str, memory_id: str) -> bool:
        """删除记忆，并保持相关状态或持久化数据一致。"""
        memory = self.get(user_id, memory_id)
        if memory is None:
            return False
        self.session.delete(memory)
        self.session.flush()
        return True


class RagRepository:
    """封装 `RagRepository` 对应实体的数据访问和作用域隔离。"""

    def __init__(self, session: Session) -> None:
        """初始化 RagRepository 及其运行依赖。"""
        self.session = session

    def get(self, user_id: str, chunk_id: str) -> RagChunk | None:
        """获取RAG并返回符合当前作用域的结果。"""
        chunk = self.session.get(RagChunk, chunk_id)
        if chunk is None:
            return None
        if chunk.owner_user_id is not None and chunk.owner_user_id != user_id:
            return None
        return chunk

    def visible_chunks(self, user_id: str, limit: int = 100) -> list[RagChunk]:
        """返回公共或当前用户私有的可见知识切片。"""
        statement = (
            select(RagChunk)
            .where((RagChunk.owner_user_id.is_(None)) | (RagChunk.owner_user_id == user_id))
            .order_by(RagChunk.created_at)
            .limit(limit)
        )
        return list(self.session.scalars(statement))


class ToolCallRepository:
    """封装 `ToolCallRepository` 对应实体的数据访问和作用域隔离。"""

    def __init__(self, session: Session) -> None:
        """初始化 ToolCallRepository 及其运行依赖。"""
        self.session = session

    def create(self, record: ToolCall) -> ToolCall:
        """创建工具、调用记录，并保持相关状态或持久化数据一致。"""
        self.session.add(record)
        self.session.flush()
        return record

    def list_for_user(self, user_id: str, limit: int = 100) -> list[ToolCall]:
        """列出用户并返回符合当前作用域的结果。"""
        statement = select(ToolCall).where(ToolCall.user_id == user_id).order_by(ToolCall.created_at).limit(limit)
        return list(self.session.scalars(statement))
