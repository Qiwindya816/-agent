"""提供 项目维护和命令行操作；本文件负责 `manage_tools` 相关实现。"""

import argparse
import json
from typing import Any

from services.tool_providers import build_provider_registry
from tools.registry import build_default_registry


def main() -> int:
    """解析命令行参数并执行 manage_tools 的主流程。"""
    parser = argparse.ArgumentParser(description="Manage TravelMind tools")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list", help="List tools and schemas")
    commands.add_parser("health", help="Show provider health")

    invoke = commands.add_parser("invoke", help="Invoke a gateway tool")
    invoke.add_argument("tool_name")
    invoke.add_argument("--user-id", default="tool_cli_user")
    invoke.add_argument("--session-id", default=None)
    invoke.add_argument("--trip-id", default=None)
    invoke.add_argument("--arguments", default="{}", help="JSON arguments")

    args = parser.parse_args()
    registry = build_default_registry()

    if args.command == "list":
        print(json.dumps(registry.descriptors(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "health":
        providers = build_provider_registry()
        print(json.dumps(providers.health_snapshot(), ensure_ascii=False, indent=2, default=str))
        return 0

    tool = registry.get(args.tool_name)
    if tool is None:
        print(f"Tool not found: {args.tool_name}")
        return 2

    from schemas.agent_state import AgentState
    from schemas.tool_gateway import GatewayCallContext

    # 仅允许直接调用经过统一网关包装的 GatewayTool。
    from tools.gateway_tool import GatewayTool

    if not isinstance(tool, GatewayTool):
        print(f"Tool is not gateway-managed: {args.tool_name}")
        return 2

    arguments = json.loads(args.arguments)
    context = GatewayCallContext(
        user_id=args.user_id,
        session_id=args.session_id,
        trip_id=args.trip_id,
    )
    state = AgentState(user_id=args.user_id, session_id=args.session_id or "default_session", trip_id=args.trip_id or "default_trip")
    result = tool.run({"mcp_arguments": arguments, "state": state, "context": context})
    payload = result.model_dump(mode="json", exclude_none=True)
    try:
        payload["data"] = json.loads(payload["data"]) if isinstance(payload.get("data"), str) else payload.get("data")
    except (TypeError, json.JSONDecodeError):
        pass
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
