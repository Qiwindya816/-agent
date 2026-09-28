from typing import Any

from exceptions.external_api import ExternalAPIError
from services.mcp_client import MCPClient
from tools.mcp_tool import RemoteMCPTool
from tools.registry import build_default_registry
from config.settings import get_settings


class FakeMCPClient:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def call_tool(self, name: str, arguments: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        self.calls.append((name, arguments))
        if self.error:
            raise self.error
        return {"pois": [{"id": "B001", "name": "人民公园"}]}, {"provider": "mcp"}


def test_remote_mcp_tool_uses_explicit_alias_and_structured_arguments() -> None:
    client = FakeMCPClient()
    tool = RemoteMCPTool("search_poi", "maps_text_search", client)

    result = tool.run({"mcp_arguments": {"keyword": "人民公园", "city": "成都"}})

    assert result.success is True
    assert client.calls == [("maps_text_search", {"keyword": "人民公园", "city": "成都"})]
    assert result.data["pois"][0]["id"] == "B001"
    assert result.metadata["provider"] == "mcp"


def test_remote_mcp_tool_rejects_missing_arguments() -> None:
    result = RemoteMCPTool("search_poi", "maps_text_search", FakeMCPClient()).run({})

    assert result.success is False
    assert result.error.code == "missing_mcp_arguments"


def test_remote_mcp_tool_normalizes_connection_failure() -> None:
    client = FakeMCPClient(error=ExternalAPIError("connection refused"))

    result = RemoteMCPTool("search_poi", "maps_text_search", client).run(
        {"mcp_arguments": {"keyword": "公园"}}
    )

    assert result.success is False
    assert result.error.code == "mcp_call_failed"
    assert result.error.retryable is True


def test_mcp_client_discovers_and_calls_official_sdk_server() -> None:
    from mcp.server import MCPServer

    server = MCPServer("travelmind-test")

    @server.tool(structured_output=True)
    def search(keyword: str) -> dict[str, Any]:
        return {"keyword": keyword, "count": 1}

    client = MCPClient("in-process", server=server)

    tools = client.list_tools()
    data, metadata = client.call_tool("search", {"keyword": "公园"})

    assert [tool["name"] for tool in tools] == ["search"]
    assert data == {"keyword": "公园", "count": 1}
    assert metadata["provider"] == "mcp"
    assert metadata["remote_tool"] == "search"


def test_mcp_client_redacts_key_from_metadata_url() -> None:
    client = MCPClient("https://mcp.amap.com/mcp?key=top-secret&tenant=demo")

    assert "top-secret" not in client.safe_url
    assert "demo" not in client.safe_url
    assert client.safe_url == "https://mcp.amap.com/mcp?key=%2A%2A%2A&tenant=%2A%2A%2A"


def test_registry_rejects_mcp_alias_that_overrides_core_tool() -> None:
    settings = get_settings()
    old_values = (settings.mcp_enabled, settings.amap_mcp_url, settings.amap_mcp_tool_map)
    settings.mcp_enabled = True
    settings.amap_mcp_url = "https://example.invalid/mcp"
    settings.amap_mcp_tool_map = {"plan_itinerary": "malicious_override"}
    try:
        try:
            build_default_registry()
            raise AssertionError("invalid MCP alias should have been rejected")
        except ValueError as exc:
            assert "plan_itinerary" in str(exc)
    finally:
        settings.mcp_enabled, settings.amap_mcp_url, settings.amap_mcp_tool_map = old_values
