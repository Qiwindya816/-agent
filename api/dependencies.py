"""提供 FastAPI 接口、依赖注入与请求处理；本文件负责 `dependencies` 相关实现。"""

from __future__ import annotations

from fastapi import Depends, Header

from db.engine import DatabaseEngine, get_database_engine
from schemas.api import UserContext
from utils.ids import validate_user_id


def get_database() -> DatabaseEngine:
    """返回进程级共享数据库引擎。"""
    return get_database_engine()


def get_current_user(x_user_id: str | None = Header(default=None)) -> UserContext:
    """从 X-User-ID 请求头解析当前用户身份。"""
    if not x_user_id:
        # 本地开发默认身份可在未接入正式认证时保持 API 可用。
        return UserContext(user_id="default_user")
    return UserContext(user_id=validate_user_id(x_user_id))
