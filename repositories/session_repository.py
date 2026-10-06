"""提供 带用户隔离的数据访问；本文件负责 `session_repository` 相关实现。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import ChatMessage, ChatSession


class SessionRepository:
    """封装 `SessionRepository` 对应实体的数据访问和作用域隔离。"""

    def __init__(self, session: Session) -> None:
        """初始化 SessionRepository 及其运行依赖。"""
        self.session = session

    def create(
        self,
        user_id: str,
        session_id: str,
        title: str | None = None,
        agent_state: dict | None = None,
        user_profile: dict | None = None,
    ) -> ChatSession:
        """创建会话，并保持相关状态或持久化数据一致。"""
        from repositories.user_repository import UserRepository

        UserRepository(self.session).require(user_id)
        chat_session = ChatSession(
            session_id=session_id,
            user_id=user_id,
            title=title,
            agent_state=agent_state,
            user_profile=user_profile,
        )
        self.session.add(chat_session)
        self.session.flush()
        return chat_session

    def get(self, user_id: str, session_id: str) -> ChatSession | None:
        """获取会话并返回符合当前作用域的结果。"""
        chat_session = self.session.get(ChatSession, session_id)
        if chat_session is None or chat_session.user_id != user_id:
            return None
        return chat_session

    def require(self, user_id: str, session_id: str) -> ChatSession:
        """返回当前用户的指定会话；不存在时抛出错误。"""
        chat_session = self.get(user_id, session_id)
        if chat_session is None:
            raise LookupError(f"Session not found for user {user_id}: {session_id}")
        return chat_session

    def list(self, user_id: str) -> list[ChatSession]:
        """列出会话并返回符合当前作用域的结果。"""
        statement = select(ChatSession).where(ChatSession.user_id == user_id).order_by(ChatSession.created_at)
        return list(self.session.scalars(statement))

    def set_current_trip(self, user_id: str, session_id: str, trip_id: str | None) -> ChatSession:
        """设置当前、旅行，并保持相关状态或持久化数据一致。"""
        chat_session = self.require(user_id, session_id)
        chat_session.current_trip_id = trip_id
        self.session.flush()
        return chat_session

    def delete(self, user_id: str, session_id: str) -> bool:
        """删除会话，并保持相关状态或持久化数据一致。"""
        chat_session = self.get(user_id, session_id)
        if chat_session is None:
            return False
        self.session.delete(chat_session)
        self.session.flush()
        return True

    def save_state(self, user_id: str, session_id: str, agent_state: dict, user_profile: dict) -> ChatSession:
        """保存状态，并保持相关状态或持久化数据一致。"""
        chat_session = self.require(user_id, session_id)
        chat_session.agent_state = agent_state
        chat_session.user_profile = user_profile
        self.session.flush()
        return chat_session

class MessageRepository:
    """封装 `MessageRepository` 对应实体的数据访问和作用域隔离。"""

    def __init__(self, session: Session) -> None:
        """初始化 MessageRepository 及其运行依赖。"""
        self.session = session

    def add(
        self,
        user_id: str,
        session_id: str,
        message_id: str,
        role: str,
        content: str,
        structured_payload: dict | None = None,
        token_count: int | None = None,
    ) -> ChatMessage:
        """添加消息，并保持相关状态或持久化数据一致。"""
        SessionRepository(self.session).require(user_id, session_id)
        message = ChatMessage(
            message_id=message_id,
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            structured_payload=structured_payload,
            token_count=token_count,
        )
        self.session.add(message)
        self.session.flush()
        return message

    def get(self, user_id: str, session_id: str, message_id: str) -> ChatMessage | None:
        """获取消息并返回符合当前作用域的结果。"""
        message = self.session.get(ChatMessage, message_id)
        if message is None or message.user_id != user_id or message.session_id != session_id:
            return None
        return message

    def list(self, user_id: str, session_id: str) -> list[ChatMessage]:
        """列出消息并返回符合当前作用域的结果。"""
        SessionRepository(self.session).require(user_id, session_id)
        statement = (
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id, ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        )
        return list(self.session.scalars(statement))
