"""提供 核心领域服务和外部服务适配；本文件负责 `tool_gateway` 相关实现。"""

from __future__ import annotations

import time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from db.engine import DatabaseEngine, get_database_engine
from db.models import ProviderHealth, ToolCall
from schemas.tool import ToolResult
from schemas.tool_gateway import GatewayCallContext, ToolDescriptor
from tools.base import BaseTool
from utils.logger import get_logger


logger = get_logger("tools")

def classify_error(exc: Exception) -> tuple[str, bool]:
    """把外部服务异常归类为稳定的网关错误码。"""
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
    """封装 `ToolGateway` 的核心数据与行为。"""

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
        """初始化 ToolGateway 及其运行依赖。"""
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
        """返回被网关包装的本地工具名称。"""
        return self.tool.name

    @property
    def description(self) -> str:
        """返回被网关包装的工具说明。"""
        return self.tool.description

    def descriptor(self) -> ToolDescriptor:
        """构建包含 Provider、Schema 和缓存策略的工具描述。"""
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
        """执行 `run` 对应的数据和流程，返回该步骤的处理结果。"""
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
                # 只有被归类为可重试的错误才进入下一次尝试。
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
        """判断 `_is_circuit_open` 对应的数据和流程，返回该步骤的处理结果。"""
        try:
            with self.database.session() as session:
                health = session.get(ProviderHealth, self.provider)
                if not health or health.circuit_state != "open" or health.success_rate >= self.failure_threshold:
                    return False
                failed_at = health.last_failure_at
                if failed_at is None:
                    return True
                if failed_at.tzinfo is None:
                    failed_at = failed_at.replace(tzinfo=timezone.utc)
                # Provider 暂时故障不能永久锁死本地开发环境；短暂冷却后，
                # 下一次调用将作为恢复探测。
                elapsed = datetime.now(timezone.utc) - failed_at
                if elapsed.total_seconds() < 0:
                    # 旧版本曾把本地墙上时间按 UTC 保存。遇到时钟偏移记录时将其视为过期，
                    # 避免错误地持续锁定 Provider。
                    return False
                return elapsed < timedelta(seconds=30)
        except Exception:
            return False

    def _cache_key(self, arguments: dict[str, Any]) -> str:
        """根据规范化工具参数生成稳定的进程内缓存键。"""
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
        """记录结构化工具日志，并在有上下文时写入审计表。"""
        logger.info(
            "tool_call_completed",
            extra={
                "event_name": "tool_call_completed",
                "request_id": context.request_id if context else None,
                "user_id": context.user_id if context else None,
                "session_id": context.session_id if context else None,
                "trip_id": context.trip_id if context else None,
                "provider": self.provider,
                "tool_name": self.tool.name,
                "success": result.success,
                "error_code": result.error.code if result.error else None,
                "elapsed_ms": latency_ms,
                "retries": retries,
                "cache_hit": cache_hit,
            },
        )
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
            # 审计写入失败绝不能阻断面向用户的工具调用主链路。
            return

    def _update_health(self, latency_ms: int, *, success: bool) -> None:
        """更新健康状态，并保持相关状态或持久化数据一致。"""
        try:
            with self.database.session() as session:
                health = session.get(ProviderHealth, self.provider)
                is_new = health is None
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
                # 首次瞬时失败不足以触发熔断；连续失败仍会打开熔断器，
                # 冷却后由 _is_circuit_open 放行恢复探测。
                health.circuit_state = "open" if not is_new and health.success_rate < 0.5 else "closed"
                if success:
                    health.last_success_at = datetime.now(timezone.utc)
                else:
                    health.last_failure_at = datetime.now(timezone.utc)
        except Exception:
            return

    # 保持 BaseTool 兼容接口，使网关可以注册到 ToolRegistry。
    def __call__(self) -> None:
        """以可调用对象形式执行 ToolGateway。"""
        raise TypeError("Use ToolGateway.run(tool_input, context) instead.")
