"""提供 带用户隔离的数据访问；本文件负责 `user_repository` 相关实现。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import User


class UserRepository:
    """封装 `UserRepository` 对应实体的数据访问和作用域隔离。"""

    def __init__(self, session: Session) -> None:
        """初始化 UserRepository 及其运行依赖。"""
        self.session = session

    def create(self, user_id: str, display_name: str | None = None) -> User:
        """创建用户，并保持相关状态或持久化数据一致。"""
        user = User(user_id=user_id, display_name=display_name)
        self.session.add(user)
        self.session.flush()
        return user

    def get(self, user_id: str) -> User | None:
        """获取用户并返回符合当前作用域的结果。"""
        return self.session.get(User, user_id)

    def require(self, user_id: str) -> User:
        """返回指定用户；不存在时抛出明确的查找错误。"""
        user = self.get(user_id)
        if user is None:
            raise LookupError(f"User not found: {user_id}")
        return user

    def update_settings(
        self,
        user_id: str,
        *,
        personalization_enabled: bool | None = None,
        long_term_memory_enabled: bool | None = None,
    ) -> User:
        """更新设置，并保持相关状态或持久化数据一致。"""
        user = self.require(user_id)
        if personalization_enabled is not None:
            user.personalization_enabled = personalization_enabled
        if long_term_memory_enabled is not None:
            user.long_term_memory_enabled = long_term_memory_enabled
        self.session.flush()
        return user

    def list_sessions(self, user_id: str):
        """列出会话列表并返回符合当前作用域的结果。"""
        from db.models import ChatSession

        user = self.require(user_id)
        return sorted(user.sessions, key=lambda item: item.created_at)

    def delete(self, user_id: str) -> bool:
        """删除用户，并保持相关状态或持久化数据一致。"""
        user = self.get(user_id)
        if user is None:
            return False
        self.session.delete(user)
        self.session.flush()
        return True
