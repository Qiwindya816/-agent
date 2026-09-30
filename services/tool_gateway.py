"""Unified Tool Gateway with audit, cache, health, and metadata."""

from __future__ import annotations

import time
from collections import OrderedDict
from datetime import datetime
from typing import Any
from uuid import uuid4

from db.engine import DatabaseEngine, get_database_engine
from db.models import ProviderHealth, ToolCall
from schemas.tool import ToolResult
from schemas.tool_gateway import GatewayCallContext, ToolDescriptor
from tools.base import BaseTool



def classify_error(exc: Exception) -> tuple[str, bool]:
    """Classify provider exceptions into stable gateway error codes."""
    message = str(exc).lower()
    if "timeout" in message or "timed out" in message:
        return "timeout", True
    if "rate" in message and "limit" in message:
        return "rate_limited", True
    if "auth" in message or "401" in message or "403" in message:
        return "auth_failed", False
    if "invalid" in message and "param" in message:
        return "invalid_params", False
    if "not found" in message or "no result" in message:
        return "no_result", False
    return "provider_error", True


DEFAULT_TOOL_TTL_SECONDS = {
    "check_weather": 3 * 60 * 60,
    "convert_currency": 60 * 60,
    "search_poi": 24 * 60 * 60,
    "geocode": 30 * 24 * 60 * 60,
    "plan_route": 30 * 60,
    "search_train_stations": 30 * 24 * 60 * 60,
    "query_train_tickets": 10 * 60,
    "query_train_price": 10 * 60,
    "query_train_transfer": 10 * 60,
    "query_train_route": 24 * 60 * 60,
}


class ToolGateway:
    """Wrap a BaseTool with auditing, cache, timeout metadata, and provider health."""

    def __init__(
        self,
        tool: BaseTool,
        provider: str,
        *,
        failure_threshold: float = 0.5,
        database: DatabaseEngine | None = None,
        cache_ttl_seconds: int = 0,
        result_expires_in_seconds: int | None = None,
        max_cache_entries: int = 256,
        retry_count: int = 0,
        retry_delay_seconds: float = 0.0,
    ) -> None:
        self.tool = tool
        self.provider = provider
        self.database = database or get_database_engine()
        self.cache_ttl_seconds = cache_ttl_seconds
        self.result_expires_in_seconds = (
            DEFAULT_TOOL_TTL_SECONDS.get(tool.name, result_expires_in_seconds)
            if result_expires_in_seconds is None
            else result_expires_in_seconds
        )
        self.max_cache_entries = max_cache_entries
        self.retry_count = retry_count
        self.retry_delay_seconds = retry_delay_seconds
        self.failure_threshold = failure_threshold
        self._cache: OrderedDict[str, tuple[float, ToolResult]] = OrderedDict()

    @property
    def name(self) -> str:
        return self.tool.name

    @property
    def description(self) -> str:
        return self.tool.description

    def descriptor(self) -> ToolDescriptor:
        from tools.schemas import TOOL_INPUT_SCHEMAS, tool_output_schema

        return ToolDescriptor(
            name=self.tool.name,
            description=self.tool.description,
            provider=self.provider,
            input_schema=TOOL_INPUT_SCHEMAS.get(self.tool.name, {}),
            output_schema=tool_output_schema(self.tool.name),
            cache_ttl_seconds=self.cache_ttl_seconds,
            result_expires_in_seconds=self.result_expires_in_seconds,
        )

    def run(self, tool_input: dict[str, Any], context: GatewayCallContext | None = None) -> ToolResult:
        """Execute a tool, cache stable calls, and persist an audit snapshot."""
        if self._is_circuit_open():
            return ToolResult.failure(
                self.tool.name,
                "circuit_open",
                "Provider circuit is open; request rejected temporarily.",
                retryable=True,
                details={"provider": self.provider},
            )
        arguments = tool_input.get("mcp_arguments") or {}
        cache_key = self._cache_key(arguments)
        now = time.monotonic()
        cached = self._cache.get(cache_key)
        if cached and cached[0] > now:
            result = cached[1].model_copy(deep=True)
            result.metadata["cache_hit"] = True
            self._record(context, arguments, result, 0, 0, True)
            return result

        started = time.perf_counter()
        result: ToolResult | None = None
        last_error: Exception | None = None
        retries = 0
        for attempt in range(self.retry_count + 1):
            try:
                result = self.tool.run(tool_input)
                break
            except Exception as exc:
                last_error = exc
                # Only retry when the classified error is retryable.
                code, _ = classify_error(exc)
                if code not in {"timeout", "rate_limited", "provider_error"} or attempt == self.retry_count:
                    break
                retries += 1
                if self.retry_delay_seconds:
                    time.sleep(self.retry_delay_seconds * (2**attempt))
        if result is None:
            assert last_error is not None
            exc = last_error
            latency = int((time.perf_counter() - started) * 1000)
            code, retryable = classify_error(exc)
            result = ToolResult.failure(
                self.tool.name,
                code,
                f"工具执行失败：{exc}",
                retryable=retryable,
                details={"provider": self.provider, "error": str(exc)},
            )
            self._update_health(latency, success=False)
            self._record(context, arguments, result, latency, retries, False)
            return result

        latency = int((time.perf_counter() - started) * 1000)
        self._update_health(latency, success=result.success)
        self._record(context, arguments, result, latency, retries, False)

        if result.success and self.cache_ttl_seconds > 0:
            self._cache[cache_key] = (time.monotonic() + self.cache_ttl_seconds, result)
            while len(self._cache) > self.max_cache_entries:
                self._cache.popitem(last=False)

        return result

    def _is_circuit_open(self) -> bool:
        """Read provider circuit state; open circuits reject calls without retry."""
        try:
            with self.database.session() as session:
                health = session.get(ProviderHealth, self.provider)
                return bool(health and health.circuit_state == "open" and health.success_rate < self.failure_threshold)
        except Exception:
            return False

    def _cache_key(self, arguments: dict[str, Any]) -> str:
        return repr(sorted(arguments.items(), key=lambda item: str(item[0])))

    def _record(
        self,
        context: GatewayCallContext | None,
        arguments: dict[str, Any],
        result: ToolResult,
        latency_ms: int,
        retries: int,
        cache_hit: bool,
    ) -> None:
        if context is None:
            return
        record = ToolCall(
            tool_call_id=f"tool_{uuid4().hex[:16]}",
            user_id=context.user_id,
            session_id=context.session_id,
            trip_id=context.trip_id,
            provider=self.provider,
            tool_name=self.tool.name,
            arguments=arguments,
            result={"success": result.success, "data": result.data, "metadata": result.metadata},
            status="success" if result.success else "failed",
            error_code=result.error.code if result.error else None,
            latency_ms=latency_ms,
            retries=retries,
            cache_hit=cache_hit,
        )
        try:
            with self.database.session() as session:
                session.add(record)
        except Exception:
            # Audit must never block the user-facing tool path.
            return

    def _update_health(self, latency_ms: int, *, success: bool) -> None:
        try:
            with self.database.session() as session:
                health = session.get(ProviderHealth, self.provider)
                if health is None:
                    health = ProviderHealth(provider_name=self.provider, status="healthy")
                    session.add(health)
                if health.average_latency is None:
                    health.average_latency = 0.0
                if health.success_rate is None:
                    health.success_rate = 0.0
                if health.average_latency == 0.0:
                    health.average_latency = float(latency_ms)
                else:
                    health.average_latency = (health.average_latency + latency_ms) / 2
                if health.success_rate == 0.0:
                    health.success_rate = 1.0 if success else 0.0
                else:
                    health.success_rate = (health.success_rate + (1.0 if success else 0.0)) / 2
                health.status = "healthy" if health.success_rate >= 0.5 else "degraded"
                health.circuit_state = "open" if health.success_rate < 0.5 else "closed"
                if success:
                    health.last_success_at = datetime.now()
                else:
                    health.last_failure_at = datetime.now()
        except Exception:
            return

    # BaseTool-compatible API so the gateway can live inside ToolRegistry.
    def __call__(self) -> None:
        raise TypeError("Use ToolGateway.run(tool_input, context) instead.")
