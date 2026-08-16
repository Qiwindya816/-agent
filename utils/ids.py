import re
from uuid import uuid4


USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$")


def validate_user_id(user_id: str) -> str:
    """清理并校验登录 ID，确保它可以安全地用于本地存储文件名。"""
    normalized = user_id.strip()
    if not USER_ID_PATTERN.fullmatch(normalized):
        raise ValueError("用户 ID 必须为 3-64 位，只能包含英文字母、数字、下划线和连字符。")
    return normalized


def new_request_id() -> str:
    """生成带 req_ 前缀的随机请求 ID。"""
    return f"req_{uuid4().hex[:12]}"


def new_session_id() -> str:
    """生成带 session_ 前缀的随机会话 ID。"""
    return f"session_{uuid4().hex[:12]}"


def new_trip_id() -> str:
    """生成带 trip_ 前缀的随机旅行 ID。"""
    return f"trip_{uuid4().hex[:12]}"
