"""提供 FastAPI 接口、依赖注入与请求处理；本文件负责 `app` 相关实现。"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.health import router as health_router
from api.middleware import (
    RateLimitExceeded,
    RateLimiter,
    request_context_middleware,
    unhandled_exception_handler,
    validation_exception_handler,
)
from api.memory import router as memory_router
from api.rag import router as rag_router
from api.sessions import router as sessions_router
from api.tools import router as tools_router
from api.trips import router as trips_router


def create_app() -> FastAPI:
    """创建并配置包含全部路由的 FastAPI 应用。"""
    app = FastAPI(
        title="TravelMind API",
        version="1.0.0",
        description="TravelMind multi-agent travel planning service.",
    )
    limiter = RateLimiter(requests_per_minute=120)

    @app.middleware("http")
    async def request_middleware(request: Request, call_next):
        """执行请求限流并注入请求级追踪上下文。"""
        try:
            limiter.check(request.headers.get("X-User-ID", "anonymous"))
            return await request_context_middleware(request, call_next)
        except RateLimitExceeded as exc:
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "rate_limited", "message": str(exc), "details": []}},
            )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in __import__("config.settings", fromlist=["get_settings"]).get_settings().api_cors_origins.split(",") if origin.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(sessions_router, prefix="/api/v1")
    app.include_router(trips_router, prefix="/api/v1")
    app.include_router(memory_router, prefix="/api/v1")
    app.include_router(rag_router, prefix="/api/v1")
    app.include_router(tools_router, prefix="/api/v1")
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    return app


app = create_app()
