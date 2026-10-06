"""提供 共享工具函数；本文件负责 `logger` 相关实现。"""

from __future__ import annotations

from contextvars import ContextVar, Token
from datetime import datetime, timezone
import json
import logging
import re
import sys
from typing import Any

from config.settings import get_settings


_LOG_CONTEXT: ContextVar[dict[str, str | None]] = ContextVar("travelmind_log_context", default={})
_CONFIGURED = False
_SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|authorization|token|secret|password)(\s*[=:]\s*)([^\s,;]+)"
)


def bind_log_context(**values: str | None) -> Token:
    """为当前异步上下文绑定请求、会话和旅行标识。"""
    current = dict(_LOG_CONTEXT.get())
    current.update({key: value for key, value in values.items() if value})
    return _LOG_CONTEXT.set(current)


def reset_log_context(token: Token) -> None:
    """恢复绑定日志上下文之前的状态。"""
    _LOG_CONTEXT.reset(token)


def redact_secrets(value: Any) -> Any:
    """递归遮盖凭据字段和文本中的敏感密钥。"""
    if isinstance(value, dict):
        return {
            key: "***" if any(word in key.lower() for word in ("token", "secret", "password", "api_key", "authorization")) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, str):
        return _SECRET_PATTERN.sub(r"\1\2***", value)
    return value


class JsonFormatter(logging.Formatter):
    """封装 `JsonFormatter` 的核心数据与行为。"""

    def format(self, record: logging.LogRecord) -> str:
        """将日志记录格式化为已脱敏的结构化 JSON。"""
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": redact_secrets(record.getMessage()),
            **{key: value for key, value in _LOG_CONTEXT.get().items() if value},
        }
        for field in (
            "event_name", "request_id", "user_id", "session_id", "trip_id", "method", "path",
            "status_code", "elapsed_ms", "provider", "tool_name", "error_code", "success",
            "retries", "cache_hit", "prompt_tokens", "completion_tokens", "total_tokens",
        ):
            if hasattr(record, field):
                payload[field] = redact_secrets(getattr(record, field))
        if record.exc_info:
            payload["exception"] = redact_secrets(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    """为当前进程配置一次文件和标准输出日志。"""
    global _CONFIGURED
    if _CONFIGURED:
        return
    settings = get_settings()
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    formatter: logging.Formatter = JsonFormatter() if settings.log_json else logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    handlers: list[logging.Handler] = [
        logging.FileHandler(settings.log_dir / "runtime.jsonl", encoding="utf-8")
    ]
    if settings.log_to_stdout:
        handlers.append(logging.StreamHandler(sys.stdout))
    root = logging.getLogger("travelmind")
    root.setLevel(level)
    root.propagate = False
    for handler in handlers:
        handler.setLevel(level)
        handler.setFormatter(formatter)
        root.addHandler(handler)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """返回 TravelMind 命名空间下的日志器。"""
    configure_logging()
    return logging.getLogger(name if name.startswith("travelmind") else f"travelmind.{name}")
