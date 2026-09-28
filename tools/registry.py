from tools.base import BaseTool
from tools.budget_tool import BudgetTool
from tools.destination_tool import DestinationTool
from tools.exchange_tool import ExchangeTool
from tools.export_tool import ExportTool
from tools.itinerary_plan_tool import ItineraryPlanTool
from tools.itinerary_refine_tool import ItineraryRefineTool
from tools.weather_tool import WeatherTool
from config.settings import get_settings
from services.mcp_client import MCPClient
from tools.mcp_tool import MCP_TOOL_ALIASES, RemoteMCPTool

# 定义一个工具注册表类 ToolRegistry，用于管理所有可用的旅行工具。
class ToolRegistry:
    def __init__(self) -> None:
        """创建空的工具名称到工具实例映射。"""
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """按工具名称注册或替换工具实例。"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        """根据名称查找工具，不存在时返回 None。"""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """返回按名称排序的已注册工具列表。"""
        return sorted(self._tools)


def build_default_registry() -> ToolRegistry:
    """创建并返回包含全部内置旅行工具的注册表。"""
    registry = ToolRegistry()
    registry.register(DestinationTool())
    registry.register(ItineraryPlanTool())
    registry.register(ItineraryRefineTool())
    registry.register(BudgetTool())
    registry.register(WeatherTool())
    registry.register(ExchangeTool())
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
            registry.register(RemoteMCPTool(local_name, remote_name, client))
    return registry
