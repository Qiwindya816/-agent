"""Request tracing middleware and unified error responses."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("travelmind.api")


async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[object]],
) -> object:
    """Attach a request ID and emit structured access logs."""
    request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:16]}"
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request_failed request_id=%s method=%s path=%s",
            request_id,
            request.method,
            request.url.path,
        )
        raise
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_completed request_id=%s method=%s path=%s status=%s elapsed_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


def _error_response(status_code: int, code: str, message: str, details: object | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or []}},
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
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
    return _error_response(422, "validation_error", "请求参数不合法。", exc.errors())


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_api_error path=%s", request.url.path)
    return _error_response(500, "internal_error", "服务内部错误。")


class RateLimitExceeded(Exception):
    """Raised when a user exceeds the local API rate limit."""


class RateLimiter:
    """Small fixed-window in-memory limiter suitable for a single API process."""

    def __init__(self, requests_per_minute: int = 120) -> None:
        self.requests_per_minute = requests_per_minute
        self.counts: dict[tuple[str, int], int] = {}

    def check(self, key: str) -> None:
        minute = int(time.time() // 60)
        bucket = (key, minute)
        count = self.counts.get(bucket, 0)
        if count >= self.requests_per_minute:
            raise RateLimitExceeded("请求过于频繁，请稍后再试。")
        self.counts[bucket] = count + 1
        # Drop old buckets cheaply.
        self.counts = {item: value for item, value in self.counts.items() if item[1] >= minute - 1}
