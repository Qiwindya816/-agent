"""提供 工作流可调用工具；本文件负责 `gateway_tool` 相关实现。"""

from __future__ import annotations

from typing import Any

from schemas.tool import ToolResult
from schemas.tool_gateway import GatewayCallContext
from services.tool_gateway import ToolGateway
from tools.base import BaseTool


class GatewayTool(BaseTool):
    """实现 `GatewayTool` 对应能力的工作流工具。"""

    def __init__(self, gateway: ToolGateway) -> None:
        """初始化 GatewayTool 及其运行依赖。"""
        self.gateway = gateway
        self.name = gateway.name
        self.description = gateway.description

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        """执行 `run` 对应的数据和流程，返回该步骤的处理结果。"""
        raw_context = tool_input.get("context")
        context = raw_context if isinstance(raw_context, GatewayCallContext) else None
        if context is None:
            state = tool_input.get("state")
            context = GatewayCallContext(
                user_id=getattr(state, "user_id", "unknown_user"),
                session_id=getattr(state, "session_id", None),
                trip_id=getattr(state, "trip_id", None),
                request_id=getattr(state, "request_id", None),
            )
        result = self.gateway.run(tool_input, context)
        self._attach_freshness(result)
        return result

    def _attach_freshness(self, result: ToolResult) -> None:
        """向工具结果附加获取时间和有效期等新鲜度元数据。"""
        from datetime import datetime

        from schemas.tool_gateway import expiry_from_now

        result.metadata.setdefault("fetched_at", datetime.now().isoformat())
        expires_at = expiry_from_now(self.gateway.result_expires_in_seconds)
        result.metadata.setdefault("expires_at", expires_at.isoformat() if expires_at else None)
