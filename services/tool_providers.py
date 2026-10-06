"""提供 核心领域服务和外部服务适配；本文件负责 `tool_providers` 相关实现。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.tool_gateway import ToolGateway
from schemas.tool import ToolResult
from tools.base import BaseTool


class _UnavailableTool(BaseTool):
    """实现 `_UnavailableTool` 对应能力的工作流工具。"""

    def __init__(self, name: str) -> None:
        """初始化 _UnavailableTool 及其运行依赖。"""
        self.name = name
        self.description = f"{name} (provider is not configured)"

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        """执行unavailable的完整业务流程并返回执行结果。"""
        return ToolResult.failure(
            self.name,
            "provider_not_configured",
            "The external provider is not configured.",
        )


@dataclass
class ToolProvider:
    """封装 `ToolProvider` 的核心数据与行为。"""

    name: str
    gateways: dict[str, ToolGateway]
    configured: bool = True

    def health(self) -> dict[str, Any]:
        """检查 API 进程及数据库连接的健康状态。"""
        from db.engine import get_database_engine
        from db.models import ProviderHealth

        snapshot: dict[str, Any] = {
            "provider": self.name,
            "tools": sorted(self.gateways),
            "configured": self.configured,
        }
        if not self.configured:
            snapshot["status"] = "unavailable"
            return snapshot
        try:
            with get_database_engine().session() as session:
                health = session.get(ProviderHealth, self.name)
                if health:
                    snapshot.update(
                        {
                            "status": health.status,
                            "success_rate": health.success_rate,
                            "average_latency": health.average_latency,
                            "circuit_state": health.circuit_state,
                            "last_success_at": health.last_success_at,
                            "last_failure_at": health.last_failure_at,
                        }
                    )
        except Exception:
            snapshot["status"] = "unknown"
        return snapshot


class ProviderRegistry:
    """封装 `ProviderRegistry` 的核心数据与行为。"""

    def __init__(self) -> None:
        """初始化 ProviderRegistry 及其运行依赖。"""
        self.providers: dict[str, ToolProvider] = {}

    def register(self, provider: ToolProvider) -> None:
        """按名称注册或替换一个外部工具提供方。"""
        self.providers[provider.name] = provider

    def get(self, name: str) -> ToolProvider | None:
        """获取服务提供方并返回符合当前作用域的结果。"""
        return self.providers.get(name)

    def list_providers(self) -> list[str]:
        """列出providers并返回符合当前作用域的结果。"""
        return sorted(self.providers)

    def health_snapshot(self) -> dict[str, dict[str, Any]]:
        """汇总所有工具提供方的当前健康状态。"""
        return {name: provider.health() for name, provider in sorted(self.providers.items())}


def build_provider_registry() -> ProviderRegistry:
    """根据默认工具注册表构建 Provider 视图。"""
    from tools.registry import build_default_registry

    registry = build_default_registry()
    providers = ProviderRegistry()
    grouped: dict[str, dict[str, ToolGateway]] = {}
    for descriptor in registry.descriptors():
        gateway = registry.get(descriptor["name"]).gateway
        grouped.setdefault(descriptor["provider"], {})[descriptor["name"]] = gateway
    for provider_name, gateways in grouped.items():
        providers.register(ToolProvider(provider_name, gateways))
    supported = {
        "amap": ("search_poi", "search_poi_detail", "geocode", "plan_route"),
        "railway-12306": (
            "search_train_stations",
            "query_train_tickets",
            "query_train_price",
            "query_train_transfer",
            "query_train_route",
        ),
    }
    for provider_name, tool_names in supported.items():
        if providers.get(provider_name) is None:
            gateways = {
                name: ToolGateway(_UnavailableTool(name), provider_name)
                for name in tool_names
            }
            providers.register(ToolProvider(provider_name, gateways, configured=False))
    return providers
