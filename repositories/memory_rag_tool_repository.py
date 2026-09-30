"""Memory, RAG, and tool call repositories with user boundaries."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db.models import MemoryEvidence, MemoryItem, RagChunk, ToolCall


class MemoryRepository:
    """Long-term memory operations isolated by user_id."""

    def __init__(self, session: Session) -> None:
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
        memory = self.session.get(MemoryItem, memory_id)
        if memory is None or memory.user_id != user_id:
            return None
        return memory

    def list(self, user_id: str) -> list[MemoryItem]:
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
        memory = self.get(user_id, memory_id)
        if memory is None:
            raise LookupError(f"Memory not found for user {user_id}: {memory_id}")
        return memory

    def delete(self, user_id: str, memory_id: str) -> bool:
        memory = self.get(user_id, memory_id)
        if memory is None:
            return False
        self.session.delete(memory)
        self.session.flush()
        return True


class RagRepository:
    """RAG chunk access separated by public and user-private ownership."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, user_id: str, chunk_id: str) -> RagChunk | None:
        chunk = self.session.get(RagChunk, chunk_id)
        if chunk is None:
            return None
        if chunk.owner_user_id is not None and chunk.owner_user_id != user_id:
            return None
        return chunk

    def visible_chunks(self, user_id: str, limit: int = 100) -> list[RagChunk]:
        statement = (
            select(RagChunk)
            .where((RagChunk.owner_user_id.is_(None)) | (RagChunk.owner_user_id == user_id))
            .order_by(RagChunk.created_at)
            .limit(limit)
        )
        return list(self.session.scalars(statement))


class ToolCallRepository:
    """Tool call audit records isolated by user/session/trip."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, record: ToolCall) -> ToolCall:
        self.session.add(record)
        self.session.flush()
        return record

    def list_for_user(self, user_id: str, limit: int = 100) -> list[ToolCall]:
        statement = select(ToolCall).where(ToolCall.user_id == user_id).order_by(ToolCall.created_at).limit(limit)
        return list(self.session.scalars(statement))
