"""Provider definitions for external tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.tool_gateway import ToolGateway


@dataclass
class ToolProvider:
    """A named collection of tools backed by one external provider."""

    name: str
    gateways: dict[str, ToolGateway]

    def health(self) -> dict[str, Any]:
        from db.engine import get_database_engine
        from db.models import ProviderHealth

        snapshot: dict[str, Any] = {
            "provider": self.name,
            "tools": sorted(self.gateways),
        }
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
    """Index providers and their gateway-backed tools."""

    def __init__(self) -> None:
        self.providers: dict[str, ToolProvider] = {}

    def register(self, provider: ToolProvider) -> None:
        self.providers[provider.name] = provider

    def get(self, name: str) -> ToolProvider | None:
        return self.providers.get(name)

    def list_providers(self) -> list[str]:
        return sorted(self.providers)

    def health_snapshot(self) -> dict[str, dict[str, Any]]:
        return {name: provider.health() for name, provider in sorted(self.providers.items())}


def build_provider_registry() -> ProviderRegistry:
    """Build the current provider view from the default tool registry."""
    from tools.registry import build_default_registry

    registry = build_default_registry()
    providers = ProviderRegistry()
    grouped: dict[str, dict[str, ToolGateway]] = {}
    for descriptor in registry.descriptors():
        gateway = registry.get(descriptor["name"]).gateway
        grouped.setdefault(descriptor["provider"], {})[descriptor["name"]] = gateway
    for provider_name, gateways in grouped.items():
        providers.register(ToolProvider(provider_name, gateways))
    return providers
