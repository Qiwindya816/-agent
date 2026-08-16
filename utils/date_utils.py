from datetime import datetime, timezone


def utc_now_iso() -> str:
    """返回带 UTC 时区信息的当前 ISO 8601 时间字符串。"""
    return datetime.now(timezone.utc).isoformat()
