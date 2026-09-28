"""外部 MCP Streamable HTTP 客户端。

SDK 在真正连接时才导入，因此未启用 MCP 的本地工作流不依赖网络或连接初始化。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from exceptions.external_api import ExternalAPIError


class MCPClient:
    """通过官方 MCP Python SDK 调用一个显式配置的远端服务。"""

    def __init__(
        self,
        url: str,
        *,
        token: str | None = None,
        timeout_seconds: float = 30,
        sse_read_timeout_seconds: float = 300,
        server: Any | None = None,
    ) -> None:
        self.url = url
        self.token = token
        self.timeout_seconds = timeout_seconds
        self.sse_read_timeout_seconds = sse_read_timeout_seconds
        self.server = server

    @property
    def safe_url(self) -> str:
        """返回隐藏全部查询参数值的 URL，供日志和元数据使用。"""
        parts = urlsplit(self.url)
        redacted_query = urlencode([(name, "***") for name, _ in parse_qsl(parts.query, keep_blank_values=True)])
        return urlunsplit((parts.scheme, parts.netloc, parts.path, redacted_query, parts.fragment))

    def list_tools(self) -> list[dict[str, Any]]:
        """连接服务并返回远端工具的名称、描述和输入 Schema。"""
        return _run_async(self._list_tools)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        """调用远端工具，并归一化结构化内容与来源元数据。"""
        return _run_async(lambda: self._call_tool(name, arguments))

    async def _list_tools(self) -> list[dict[str, Any]]:
        async with self._connect() as client:
            result = await client.list_tools()
            return [
                {
                    "name": tool.name,
                    "description": getattr(tool, "description", None),
                    "input_schema": getattr(tool, "input_schema", None),
                }
                for tool in result.tools
            ]

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> tuple[Any, dict[str, Any]]:
        async with self._connect() as client:
            result = await client.call_tool(name, arguments)
            if getattr(result, "is_error", False):
                raise ExternalAPIError(_content_text(getattr(result, "content", [])) or f"MCP 工具 {name} 返回错误。")
            structured = getattr(result, "structured_content", None)
            data = structured if structured is not None else _content_value(getattr(result, "content", []))
            metadata = {
                "provider": "mcp",
                "mcp_url": self.safe_url,
                "remote_tool": name,
                "protocol_version": str(getattr(client, "protocol_version", "unknown")),
            }
            return data, metadata

    @asynccontextmanager
    async def _connect(self):
        try:
            from mcp import Client
        except ImportError as exc:
            raise ExternalAPIError("缺少 MCP SDK，请执行 pip install -r requirements.txt。") from exc

        try:
            if self.server is not None:
                async with Client(self.server, read_timeout_seconds=self.timeout_seconds) as client:
                    yield client
                return
            if not self.token:
                async with Client(self.url, read_timeout_seconds=self.timeout_seconds) as client:
                    yield client
                return

            import httpx2
            from mcp.client.streamable_http import streamable_http_client

            headers = {"Authorization": f"Bearer {self.token}"}
            timeout = httpx2.Timeout(self.timeout_seconds, read=self.sse_read_timeout_seconds)
            async with httpx2.AsyncClient(headers=headers, timeout=timeout) as http_client:
                transport = streamable_http_client(self.url, http_client=http_client)
                async with Client(transport, read_timeout_seconds=self.timeout_seconds) as client:
                    yield client
        except ExternalAPIError:
            raise
        except Exception as exc:
            message = str(exc).replace(self.url, self.safe_url)
            if self.token:
                message = message.replace(self.token, "***")
            raise ExternalAPIError(f"MCP 连接或调用失败：{message}") from exc


def _run_async(factory: Callable[[], Awaitable[Any]]) -> Any:
    """从当前同步工具链安全执行异步 MCP 调用。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="travelmind-mcp") as pool:
        return pool.submit(lambda: asyncio.run(factory())).result()


def _content_text(content: list[Any]) -> str:
    return "\n".join(str(item.text) for item in content if getattr(item, "text", None))


def _content_value(content: list[Any]) -> Any:
    text = _content_text(content)
    if text:
        return text
    return [item.model_dump(mode="json") if hasattr(item, "model_dump") else str(item) for item in content]
