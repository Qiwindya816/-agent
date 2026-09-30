"""Tests for the unified Tool Gateway."""

from pathlib import Path
from typing import Any

import pytest

from db.engine import DatabaseEngine
from schemas.agent_state import AgentState
from schemas.route import RouteResult
from schemas.tool import ToolResult
from schemas.tool_gateway import GatewayCallContext
from services.tool_gateway import ToolGateway
from tools.base import BaseTool
from tools.gateway_tool import GatewayTool


class FakeTool(BaseTool):
    def __init__(self, name: str, calls: list[dict[str, Any]], *, fail: bool = False) -> None:
        self.name = name
        self.description = name
        self.calls = calls
        self.fail = fail

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        self.calls.append(tool_input)
        if self.fail:
            raise RuntimeError("boom")
        return ToolResult.ok(self.name, {"ok": True}, {"provider": "fake"})


@pytest.fixture()
def database(tmp_path: Path) -> DatabaseEngine:
    engine = DatabaseEngine(f"sqlite+pysqlite:///{tmp_path / 'gateway.db'}")
    engine.create_all()
    yield engine
    engine.dispose()


def test_gateway_records_audit_and_provider_health(database: DatabaseEngine) -> None:
    calls: list[dict[str, Any]] = []
    gateway = ToolGateway(FakeTool("check_weather", calls), "open-meteo", database=database)

    result = gateway.run(
        {"mcp_arguments": {"location": "成都"}},
        GatewayCallContext(user_id="user_a", session_id="session_a", trip_id="trip_a"),
    )

    assert result.success is True
    with database.session() as session:
        from db.models import ProviderHealth, ToolCall

        record = session.query(ToolCall).one()
        assert record.user_id == "user_a"
        assert record.provider == "open-meteo"
        assert record.status == "success"
        assert record.latency_ms >= 0

        health = session.get(ProviderHealth, "open-meteo")
        assert health is not None
        assert health.status == "healthy"


def test_gateway_failure_is_recorded_without_raising(database: DatabaseEngine) -> None:
    calls: list[dict[str, Any]] = []
    gateway = ToolGateway(FakeTool("check_weather", calls, fail=True), "open-meteo", database=database)

    result = gateway.run(
        {"mcp_arguments": {"location": "成都"}},
        GatewayCallContext(user_id="user_a"),
    )

    assert result.success is False
    assert result.error.code == "provider_error"
    with database.session() as session:
        from db.models import ToolCall

        record = session.query(ToolCall).one()
        assert record.status == "failed"
        assert record.error_code == "provider_error"


def test_gateway_cache_prevents_repeated_calls(database: DatabaseEngine) -> None:
    calls: list[dict[str, Any]] = []
    gateway = ToolGateway(
        FakeTool("check_weather", calls),
        "open-meteo",
        database=database,
        cache_ttl_seconds=60,
    )
    context = GatewayCallContext(user_id="user_a")

    first = gateway.run({"mcp_arguments": {"location": "成都"}}, context)
    second = gateway.run({"mcp_arguments": {"location": "成都"}}, context)

    assert len(calls) == 1
    assert first.metadata.get("cache_hit") is not True
    assert second.metadata["cache_hit"] is True


def test_gateway_tool_attaches_freshness_metadata(database: DatabaseEngine) -> None:
    calls: list[dict[str, Any]] = []
    tool = GatewayTool(ToolGateway(FakeTool("check_weather", calls), "open-meteo", database=database))
    state = AgentState(user_id="user_a", session_id="session_a")

    result = tool.run({"mcp_arguments": {"location": "成都"}, "state": state})

    assert result.success is True
    assert "fetched_at" in result.metadata
    assert "expires_at" in result.metadata


def test_executor_runs_external_tools_through_gateway(database: DatabaseEngine) -> None:
    from multi_agent.executor import ToolExecutor
    from tools.registry import ToolRegistry

    calls: list[dict[str, Any]] = []
    registry = ToolRegistry()
    registry.register_gateway(FakeTool("check_weather", calls), "open-meteo")
    # Inject the test database into the gateway created by register_gateway.
    gateway_tool = registry.get("check_weather")
    gateway_tool.gateway.database = database
    executor = ToolExecutor(registry)
    state = AgentState(user_id="user_a", session_id="session_a")

    result = executor.execute(
        RouteResult(intent="weather", tool_name="check_weather", confidence=0.9),
        "查询成都天气",
        state,
    )

    assert result.success is True
    with database.session() as session:
        from db.models import ToolCall

        assert session.query(ToolCall).count() == 1


def test_gateway_classifies_provider_errors(database: DatabaseEngine) -> None:
    from services.tool_gateway import classify_error

    assert classify_error(RuntimeError("Connection timed out")) == ("timeout", True)
    assert classify_error(RuntimeError("Rate limit exceeded")) == ("rate_limited", True)
    assert classify_error(RuntimeError("401 auth failed")) == ("auth_failed", False)
    assert classify_error(RuntimeError("INVALID_PARAMS")) == ("invalid_params", False)
    assert classify_error(RuntimeError("provider boom")) == ("provider_error", True)


def test_registry_exposes_gateway_descriptors(database: DatabaseEngine) -> None:
    from tools.registry import ToolRegistry

    calls: list[dict[str, Any]] = []
    registry = ToolRegistry()
    registry.register_gateway(FakeTool("check_weather", calls), "open-meteo", cache_ttl_seconds=60)

    descriptors = registry.descriptors()

    assert descriptors[0]["name"] == "check_weather"
    assert descriptors[0]["provider"] == "open-meteo"
    assert descriptors[0]["cache_ttl_seconds"] == 60
    assert descriptors[0]["input_schema"]["required"] == ["location"]


def test_provider_registry_groups_gateway_tools() -> None:
    from services.tool_providers import ProviderRegistry, build_provider_registry

    providers = build_provider_registry()

    assert providers.list_providers() == ["amap", "frankfurter", "open-meteo", "railway-12306"]
    assert "query_train_tickets" in providers.get("railway-12306").gateways
    assert "search_poi" in providers.get("amap").gateways


def test_descriptor_exposes_output_schema() -> None:
    from services.tool_gateway import ToolGateway

    gateway = ToolGateway(FakeTool("query_train_tickets", []), "railway-12306")
    descriptor = gateway.descriptor()

    assert descriptor.output_schema["items"]["x-model"] == "NormalizedTrainTicket"


def test_gateway_retries_retryable_failures(database: DatabaseEngine) -> None:
    from services.tool_gateway import ToolGateway

    class FlakyTool(BaseTool):
        name = "check_weather"
        description = "weather"
        attempts = 0

        def run(self, tool_input: dict[str, Any]) -> ToolResult:
            type(self).attempts += 1
            if type(self).attempts == 1:
                raise RuntimeError("Connection timed out")
            return ToolResult.ok(self.name, {"ok": True})

    gateway = ToolGateway(
        FlakyTool(),
        "open-meteo",
        database=database,
        retry_count=2,
        retry_delay_seconds=0,
    )

    result = gateway.run({"mcp_arguments": {"location": "成都"}}, GatewayCallContext(user_id="user_a"))

    assert result.success is True
    with database.session() as session:
        from db.models import ToolCall

        record = session.query(ToolCall).one()
        assert record.retries == 1


def test_gateway_rejects_when_circuit_is_open(database: DatabaseEngine) -> None:
    from datetime import datetime

    from db.models import ProviderHealth

    with database.session() as session:
        session.add(
            ProviderHealth(
                provider_name="open-meteo",
                status="degraded",
                success_rate=0.0,
                average_latency=100,
                circuit_state="open",
            )
        )

    calls: list[dict[str, Any]] = []
    gateway = ToolGateway(FakeTool("check_weather", calls), "open-meteo", database=database)

    result = gateway.run({"mcp_arguments": {"location": "成都"}}, GatewayCallContext(user_id="user_a"))

    assert result.success is False
    assert result.error.code == "circuit_open"
    assert calls == []
