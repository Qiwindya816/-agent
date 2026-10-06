"""提供 项目维护和命令行操作；本文件负责 `manage_xhs` 相关实现。"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from config.settings import get_settings
from db.engine import DatabaseEngine
from services.xhs_ingestion import XhsMcpService, XhsPilotIngestionService


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "xhs_pilot.json"


def _print(payload: object) -> None:
    """以 UTF-8 中文友好的 JSON 格式打印命令结果。"""
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def tools(_: argparse.Namespace) -> int:
    """列出当前小红书 MCP 暴露的只读工具。"""
    _print(XhsMcpService().list_tools())
    return 0


def status(args: argparse.Namespace) -> int:
    """显示小红书 MCP 登录状态和可用工具状态。"""
    service = XhsMcpService()
    payload: dict[str, object] = {"accounts": service.list_accounts()}
    if args.check_auth:
        payload["auth"] = service.check_auth(args.account)
    _print(payload)
    return 0


def login(args: argparse.Namespace) -> int:
    """启动小红书 MCP 登录流程并展示操作提示。"""
    payload = XhsMcpService().begin_login(args.name)
    _print(payload)
    qr_url = payload.get("qrCodeUrl")
    if args.open_browser and isinstance(qr_url, str):
        webbrowser.open(qr_url)
    return 0


def check_login(args: argparse.Namespace) -> int:
    """检查登录状态并返回校验结果。"""
    _print(XhsMcpService().check_login(args.session_id))
    return 0


def verify(args: argparse.Namespace) -> int:
    """验证试点配置、MCP 连接和 RAG 来源是否可用。"""
    _print(XhsMcpService().submit_verification(args.session_id, args.code))
    return 0


def crawl(args: argparse.Namespace) -> int:
    """按命令行城市、主题和数量执行小红书试点采集。"""
    settings = get_settings()
    database = DatabaseEngine(settings.database_url)
    result = XhsPilotIngestionService(database=database).run(
        Path(args.config),
        account=args.account,
        cities=set(args.city) if args.city else None,
        themes=set(args.theme) if args.theme else None,
        notes_per_cell=args.notes_per_cell,
        embed=not args.no_embed,
    )
    _print(result.to_dict())
    return 0 if not result.errors else 2


def main() -> int:
    """解析命令行参数并执行 manage_xhs 的主流程。"""
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in {"utf-8", "utf8"}:
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="管理 TravelMind 小红书只读知识库采集")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("tools", help="检查服务端只读工具白名单").set_defaults(func=tools)

    status_parser = commands.add_parser("status", help="查看已登录账号")
    status_parser.add_argument("--account")
    status_parser.add_argument("--check-auth", action="store_true")
    status_parser.set_defaults(func=status)

    login_parser = commands.add_parser("login", help="开始扫码登录")
    login_parser.add_argument("--name", help="本地账号别名")
    login_parser.add_argument("--no-open-browser", dest="open_browser", action="store_false")
    login_parser.set_defaults(func=login, open_browser=True)

    check_parser = commands.add_parser("check-login", help="扫码后检查登录状态")
    check_parser.add_argument("session_id")
    check_parser.set_defaults(func=check_login)

    verify_parser = commands.add_parser("verify", help="需要短信验证时提交验证码")
    verify_parser.add_argument("session_id")
    verify_parser.add_argument("code")
    verify_parser.set_defaults(func=verify)

    crawl_parser = commands.add_parser("crawl", help="运行城市/主题试点采集并导入 RAG")
    crawl_parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    crawl_parser.add_argument("--account", help="指定 MCP 中的账号名或账号 ID")
    crawl_parser.add_argument("--city", action="append", help="只采集指定城市，可重复传入")
    crawl_parser.add_argument("--theme", action="append", help="只采集指定主题 ID/名称，可重复传入")
    crawl_parser.add_argument("--notes-per-cell", type=int, help="每个城市×主题最多导入数")
    crawl_parser.add_argument("--no-embed", action="store_true", help="只验证采集和入库，不调用向量模型")
    crawl_parser.set_defaults(func=crawl)

    args = parser.parse_args()
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
