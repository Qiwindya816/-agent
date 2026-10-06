from tools.base import BaseTool
from tools.budget_tool import BudgetTool
from tools.destination_tool import DestinationTool
from tools.exchange_tool import ExchangeTool
from tools.export_tool import ExportTool
from tools.itinerary_plan_tool import ItineraryPlanTool
from tools.itinerary_edit_tool import ItineraryEditTool
from tools.itinerary_refine_tool import ItineraryRefineTool
from tools.weather_tool import WeatherTool
from typing import Any

from config.settings import get_settings
from services.mcp_client import MCPClient
from tools.gateway_tool import GatewayTool
from tools.mcp_tool import MCP_TOOL_ALIASES, RAILWAY_MCP_TOOL_ALIASES, RemoteMCPTool
from services.tool_gateway import ToolGateway

# 定义一个工具注册表类 ToolRegistry，用于管理所有可用的旅行工具。
class ToolRegistry:
    """集中注册、查询并描述工作流允许调用的旅行工具。"""
    def __init__(self) -> None:
        """创建空的工具名称到工具实例映射。"""
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """按工具名称注册或替换工具实例。"""
        self._tools[tool.name] = tool

    def register_gateway(self, tool: BaseTool, provider: str, *, cache_ttl_seconds: int = 0) -> None:
        """注册 `register_gateway` 对应的数据和流程，返回该步骤的处理结果。"""
        gateway = ToolGateway(tool, provider, cache_ttl_seconds=cache_ttl_seconds)
        self.register(GatewayTool(gateway))

    def get(self, name: str) -> BaseTool | None:
        """根据名称查找工具，不存在时返回 None。"""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """返回按名称排序的已注册工具列表。"""
        return sorted(self._tools)

    def descriptors(self) -> list[dict[str, Any]]:
        """返回所有 Gateway 工具的描述和输入 Schema。"""
        from tools.gateway_tool import GatewayTool

        return [
            tool.gateway.descriptor().model_dump(mode="json")
            for tool in self._tools.values()
            if isinstance(tool, GatewayTool)
        ]


def build_default_registry() -> ToolRegistry:
    """创建并返回包含全部内置旅行工具的注册表。"""
    registry = ToolRegistry()
    registry.register(DestinationTool())
    registry.register(ItineraryPlanTool())
    registry.register(ItineraryRefineTool())
    registry.register(ItineraryEditTool())
    registry.register(BudgetTool())
    registry.register_gateway(WeatherTool(), "open-meteo", cache_ttl_seconds=3 * 60 * 60)
    registry.register_gateway(ExchangeTool(), "frankfurter", cache_ttl_seconds=60 * 60)
    registry.register(ExportTool())
    settings = get_settings()
    if settings.mcp_enabled and settings.amap_mcp_url:
        invalid_aliases = set(settings.amap_mcp_tool_map) - MCP_TOOL_ALIASES
        if invalid_aliases:
            raise ValueError(f"不允许的 MCP 工具别名：{', '.join(sorted(invalid_aliases))}")
        client = MCPClient(
            settings.amap_mcp_url,
            token=settings.amap_mcp_token,
            timeout_seconds=settings.mcp_timeout_seconds,
            sse_read_timeout_seconds=settings.mcp_sse_read_timeout_seconds,
        )
        for local_name, remote_name in settings.amap_mcp_tool_map.items():
            registry.register_gateway(
                RemoteMCPTool(local_name, remote_name, client),
                "amap",
                cache_ttl_seconds=1800 if local_name == "plan_route" else 3600,
            )

    if settings.railway_mcp_enabled and settings.railway_mcp_url:
        invalid_aliases = set(settings.railway_mcp_tool_map) - RAILWAY_MCP_TOOL_ALIASES
        if invalid_aliases:
            raise ValueError(f"不允许的铁路 MCP 工具别名：{', '.join(sorted(invalid_aliases))}")
        client = MCPClient(
            settings.railway_mcp_url,
            token=settings.railway_mcp_token,
            timeout_seconds=settings.railway_mcp_timeout_seconds,
            sse_read_timeout_seconds=settings.railway_mcp_sse_read_timeout_seconds,
        )
        for local_name, remote_name in settings.railway_mcp_tool_map.items():
            ttl = 600 if local_name.startswith("query_train_") else 3600
            registry.register_gateway(
                RemoteMCPTool(local_name, remote_name, client),
                "railway-12306",
                cache_ttl_seconds=ttl,
            )
    return registry
