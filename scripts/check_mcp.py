import json

from config.settings import get_settings
from services.mcp_client import MCPClient


def main() -> int:
    """连接已配置的 MCP Server 并打印其 tools/list 结果。"""
    settings = get_settings()
    if not settings.amap_mcp_url:
        print("未配置 AMAP_MCP_URL。")
        return 2
    client = MCPClient(
        settings.amap_mcp_url,
        token=settings.amap_mcp_token,
        timeout_seconds=settings.mcp_timeout_seconds,
        sse_read_timeout_seconds=settings.mcp_sse_read_timeout_seconds,
    )
    try:
        tools = client.list_tools()
    except Exception as exc:
        print(f"MCP 连接失败：{exc}")
        return 1
    print(json.dumps(tools, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
