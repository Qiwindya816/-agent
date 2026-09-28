from typing import Any, Protocol

from exceptions.external_api import ExternalAPIError
from schemas.tool import ToolResult
from tools.base import BaseTool


MCP_TOOL_ALIASES = frozenset({"search_poi", "geocode", "plan_route"})


class MCPCaller(Protocol):
    def call_tool(self, name: str, arguments: dict[str, Any]) -> tuple[Any, dict[str, Any]]: ...


class RemoteMCPTool(BaseTool):
    """把一个白名单内的远端 MCP 工具暴露为本地 ToolRegistry 工具。"""

    def __init__(self, name: str, remote_name: str, client: MCPCaller) -> None:
        self.name = name
        self.remote_name = remote_name
        self.client = client
        self.description = f"调用 MCP 工具 {remote_name}。"

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        arguments = tool_input.get("mcp_arguments") or {}
        if not isinstance(arguments, dict) or not arguments:
            return ToolResult.failure(
                self.name,
                "missing_mcp_arguments",
                f"调用 {self.name} 缺少结构化 arguments。",
            )
        try:
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
