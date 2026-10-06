"""提供 数据库模型、连接与初始化；本文件负责 `engine` 相关实现。"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config.settings import get_settings


class DatabaseEngine:
    """封装 `DatabaseEngine` 的核心数据与行为。"""

    def __init__(self, database_url: str | None = None, *, echo: bool | None = None) -> None:
        """初始化 DatabaseEngine 及其运行依赖。"""
        settings = get_settings()
        self.url = database_url or settings.database_url
        self.echo = settings.database_echo if echo is None else echo
        connect_args = {"connect_timeout": 5} if self.url.startswith("postgresql") else {}
        self.engine = create_engine(
            self.url,
            echo=self.echo,
            future=True,
            connect_args=connect_args,
        )
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False, future=True)

    def create_all(self) -> None:
        """创建开发和测试所需的数据表。"""
        from db import Base

        Base.metadata.create_all(self.engine)

    def dispose(self) -> None:
        """关闭连接池并释放数据库引擎资源。"""
        self.engine.dispose()

    @contextmanager
    def session(self) -> Iterator[Session]:
        """提供自动提交、异常回滚并最终关闭的数据库会话。"""
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


_engine: DatabaseEngine | None = None


def get_database_engine() -> DatabaseEngine:
    """延迟创建并返回进程级数据库引擎。"""
    global _engine
    if _engine is None:
        _engine = DatabaseEngine()
    return _engine


def reset_database_engine(database_url: str | None = None) -> DatabaseEngine:
    """释放旧连接并重建进程级数据库引擎。"""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = DatabaseEngine(database_url)
    return _engine
