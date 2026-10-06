import json
from typing import Any, Protocol

from exceptions.external_api import ExternalAPIError
from schemas.tool import ToolResult
from tools.base import BaseTool


MCP_TOOL_ALIASES = frozenset({"search_poi", "search_poi_detail", "geocode", "plan_route"})
RAILWAY_MCP_TOOL_ALIASES = frozenset(
    {
        "search_train_stations",
        "query_train_tickets",
        "query_train_price",
        "query_train_transfer",
        "query_train_route",
    }
)


class MCPCaller(Protocol):
    """约束 MCP 客户端必须提供的远端工具调用接口。"""

    def call_tool(self, name: str, arguments: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        """调用指定 MCP 工具并返回数据及调用元信息。"""
        ...


class RemoteMCPTool(BaseTool):
    """把一个白名单内的远端 MCP 工具暴露为本地 ToolRegistry 工具。"""

    def __init__(self, name: str, remote_name: str, client: MCPCaller) -> None:
        """初始化 RemoteMCPTool 及其运行依赖。"""
        self.name = name
        self.remote_name = remote_name
        self.client = client
        self.description = f"调用 MCP 工具 {remote_name}。"

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        """校验并转换参数后调用远端 MCP 工具。"""
        arguments = tool_input.get("mcp_arguments") or {}
        if self.name == "geocode":
            arguments = _normalize_geocode_arguments(arguments)
        if self.name == "plan_route":
            arguments = _normalize_route_arguments(arguments)
            if not arguments:
                return ToolResult.failure(
                    self.name,
                    "missing_route_coordinates",
                    "路线规划需要先解析起终点经纬度坐标。",
                )
        if not isinstance(arguments, dict) or not arguments:
            return ToolResult.failure(
                self.name,
                "missing_mcp_arguments",
                f"调用 {self.name} 缺少结构化 arguments。",
            )
        try:
            if self.name == "geocode" and isinstance(arguments.get("addresses"), list):
                return self._run_geocode_addresses(arguments)
            data, metadata = self.client.call_tool(self.remote_name, arguments)
            return ToolResult.ok(self.name, data, metadata)
        except ExternalAPIError as exc:
            return ToolResult.failure(
                self.name,
                "mcp_call_failed",
                str(exc),
                retryable=True,
                details={"remote_tool": self.remote_name},
            )
        except Exception as exc:
            return ToolResult.failure(
                self.name,
                "mcp_unexpected_error",
                "MCP 工具调用出现未预期错误。",
                details={"remote_tool": self.remote_name, "error": str(exc)},
            )

    def _run_geocode_addresses(self, arguments: dict[str, Any]) -> ToolResult:
        """一次解析多个路线地点，并保留地址到坐标的映射。"""
        addresses = [str(item).strip() for item in arguments.get("addresses", []) if str(item).strip()]
        if not addresses:
            return ToolResult.failure(self.name, "missing_mcp_arguments", "缺少待解析的地址。")

        results = []
        unresolved = []
        city = str(arguments.get("city") or "")
        for address in addresses:
            try:
                data, _ = self.client.call_tool(self.remote_name, {"address": address, "city": city})
            except Exception as exc:
                unresolved.append({"address": address, "error": str(exc)})
                continue
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError:
                    data = {}
            candidates = data.get("results") if isinstance(data, dict) else []
            first = candidates[0] if candidates else {}
            location = first.get("location") if isinstance(first, dict) else None
            if not location:
                unresolved.append({"address": address, "error": "没有解析到经纬度坐标"})
                continue
            results.append(
                {
                    "address": address,
                    "location": str(location),
                    "city": str(first.get("city") or city or ""),
                }
            )
        if not results:
            return ToolResult.failure(
                self.name,
                "geocode_no_location",
                "没有解析到可用的经纬度坐标。",
                retryable=True,
                details={"unresolved": unresolved},
            )
        return ToolResult.ok(
            self.name,
            {"results": results, "unresolved": unresolved},
            {"provider": "mcp", "remote_tool": self.remote_name},
        )


def _normalize_geocode_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """兼容单地址和高德 geocode Schema，支持路线前置解析。"""
    if not isinstance(arguments, dict):
        return arguments
    addresses = arguments.get("addresses")
    if isinstance(addresses, list):
        return {
            "addresses": [str(address) for address in addresses if str(address).strip()],
            "city": str(arguments.get("city") or ""),
        }
    return arguments


def _normalize_route_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """移除本地通用 mode 字段，并补齐高德公交路线的城市字段。"""
    if not isinstance(arguments, dict):
        return arguments
    normalized = dict(arguments)
    if not normalized.get("origin") or not normalized.get("destination"):
        return {}
    normalized.pop("mode", None)
    city = str(normalized.get("city") or "北京")
    cityd = str(normalized.get("cityd") or normalized.get("destination_city") or city)
    normalized["city"] = city
    normalized["cityd"] = cityd
    return normalized
