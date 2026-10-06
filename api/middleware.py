"""提供 FastAPI 接口、依赖注入与请求处理；本文件负责 `middleware` 相关实现。"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from utils.logger import bind_log_context, get_logger, reset_log_context

logger = get_logger("api")


async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[object]],
) -> object:
    """注入请求 ID，并输出结构化访问日志。"""
    request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:16]}"
    request.state.request_id = request_id
    context_token = bind_log_context(
        request_id=request_id,
        user_id=request.headers.get("X-User-ID"),
        session_id=request.headers.get("X-Session-ID"),
        trip_id=request.headers.get("X-Trip-ID"),
    )
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed", extra={"event_name": "request_failed", "method": request.method, "path": request.url.path})
        reset_log_context(context_token)
        raise
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_completed",
        extra={
            "event_name": "request_completed",
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "elapsed_ms": elapsed_ms,
        },
    )
    reset_log_context(context_token)
    return response


def _error_response(status_code: int, code: str, message: str, details: object | None = None) -> JSONResponse:
    """构造统一格式的 API 错误响应。"""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or []}},
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """将 FastAPI HTTP 异常转换为统一错误响应。"""
    code = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        429: "rate_limited",
    }.get(exc.status_code, "http_error")
    return _error_response(exc.status_code, code, str(exc.detail), exc.detail if isinstance(exc.detail, list) else None)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """将请求参数校验错误转换为统一错误响应。"""
    return _error_response(422, "validation_error", "请求参数不合法。", exc.errors())


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """记录未处理异常并返回安全的服务器错误响应。"""
    logger.exception("unhandled_api_error path=%s", request.url.path)
    return _error_response(500, "internal_error", "服务内部错误。")


class RateLimitExceeded(Exception):
    """封装 `RateLimitExceeded` 的核心数据与行为。"""


class RateLimiter:
    """封装 `RateLimiter` 的核心数据与行为。"""

    def __init__(self, requests_per_minute: int = 120) -> None:
        """初始化 RateLimiter 及其运行依赖。"""
        self.requests_per_minute = requests_per_minute
        self.counts: dict[tuple[str, int], int] = {}

    def check(self, key: str) -> None:
        """检查调用方在当前分钟是否超过请求频率限制。"""
        minute = int(time.time() // 60)
        bucket = (key, minute)
        count = self.counts.get(bucket, 0)
        if count >= self.requests_per_minute:
            raise RateLimitExceeded("请求过于频繁，请稍后再试。")
        self.counts[bucket] = count + 1
        # 以较低开销移除过期的分钟计数桶。
        self.counts = {item: value for item, value in self.counts.items() if item[1] >= minute - 1}
