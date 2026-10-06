"""提供 TravelMind 项目功能；本文件负责 `main` 相关实现。"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from multi_agent.workflow import MultiAgentTravelWorkflow
from utils.ids import validate_user_id


PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
BACKEND_URL = "http://127.0.0.1:8000"
FRONTEND_URL = "http://127.0.0.1:5173"


def run_cli() -> None:
    """运行原有的终端交互式旅行助手。"""
    print("欢迎使用 TravelMind LangGraph 多智能体版本。")
    while True:
        try:
            user_id = validate_user_id(input("请输入用户 ID 登录：\n"))
            break
        except ValueError as exc:
            print(exc)

    workflow = MultiAgentTravelWorkflow(user_id=user_id)
    print(f"登录成功：{user_id}")
    print(f"本次会话 ID：{workflow.session_id}")
    print("输入 q、quit 或 exit 退出。")
    while True:
        user_input = input("\n请输入旅行需求：\n").strip()
        if user_input.lower() in {"q", "quit", "exit"}:
            print("已退出 TravelMind。")
            return
        if not user_input:
            print("请输入有效的旅行需求。")
            continue
        print("\n" + workflow.run(user_input))


def _url_ready(url: str, timeout: float = 1.0) -> bool:
    """探测指定 URL 是否已经能够正常响应。"""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 500
    except (OSError, urllib.error.URLError):
        return False


def _find_node() -> Path:
    """查找node并返回符合当前作用域的结果。"""
    candidates: list[Path] = []
    discovered = shutil.which("node")
    if discovered:
        candidates.append(Path(discovered))
    if os.name == "nt":
        candidates.extend(
            [
                Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs" / "node.exe",
                Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "nodejs" / "node.exe",
            ]
        )
    else:
        candidates.extend([Path("/usr/local/bin/node"), Path("/usr/bin/node")])

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("未找到 Node.js。请先安装 Node.js LTS，然后重新运行 main.py。")


def _xhs_mcp_entry() -> Path:
    """返回本地只读小红书 MCP 服务入口。"""
    runtime_root = PROJECT_ROOT / "integrations" / "xhs-mcp-runtime"
    entry = runtime_root / "read-only-server.mjs"
    dependency = runtime_root / "node_modules" / "@sillyl12324" / "xhs-mcp" / "package.json"
    sqlite_binding = runtime_root / "node_modules" / "better-sqlite3" / "build" / "Release" / "better_sqlite3.node"
    if entry.is_file() and dependency.is_file() and sqlite_binding.is_file():
        return entry
    raise RuntimeError("小红书 MCP 运行环境不完整，请执行：python scripts/setup_xhs_mcp.py")


def _vite_entry() -> Path:
    """定位本地安装的 Vite JavaScript 启动入口。"""
    entry = FRONTEND_ROOT / "node_modules" / "vite" / "bin" / "vite.js"
    if not entry.is_file():
        raise RuntimeError(
            "前端依赖尚未安装。请先在 frontend 目录执行 npm install，然后重新运行 main.py。"
        )
    return entry


def _wait_until_ready(
    url: str,
    label: str,
    process: subprocess.Popen[bytes] | None,
    timeout: float = 90.0,
) -> None:
    """等待子进程及其健康检查地址进入可用状态。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _url_ready(url):
            print(f"[OK] {label}已就绪：{url}")
            return
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"{label}启动失败，退出码：{process.returncode}")
        time.sleep(0.25)
    raise RuntimeError(f"等待{label}启动超时：{url}")


def _stop_process(process: subprocess.Popen[bytes], label: str) -> None:
    """平滑停止子进程，并在超时后强制终止。"""
    if process.poll() is not None:
        return
    print(f"正在关闭{label}……")
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def run_web(*, open_browser: bool = True) -> int:
    """启动并监管后端与前端开发服务器。"""
    children: list[tuple[str, subprocess.Popen[bytes]]] = []
    backend_process: subprocess.Popen[bytes] | None = None
    frontend_process: subprocess.Popen[bytes] | None = None
    xhs_process: subprocess.Popen[bytes] | None = None

    try:
        from config.settings import get_settings

        settings = get_settings()
        xhs_health_url = f"http://127.0.0.1:{settings.xhs_mcp_port}/health"
        if settings.xhs_mcp_enabled:
            if _url_ready(xhs_health_url):
                print(f"[OK] 检测到小红书 MCP 已经运行：{settings.xhs_mcp_url}")
            else:
                node = _find_node()
                xhs_entry = _xhs_mcp_entry()
                xhs_environment = os.environ.copy()
                xhs_environment.update(
                    {
                        "XHS_MCP_PORT": str(settings.xhs_mcp_port),
                        "XHS_MCP_DATA_DIR": str(settings.xhs_mcp_data_dir.resolve()),
                        "XHS_MCP_HEADLESS": "true" if settings.xhs_mcp_headless else "false",
                        "XHS_MCP_REQUEST_INTERVAL": str(settings.xhs_mcp_request_interval_ms),
                    }
                )
                print("正在启动小红书知识库 MCP……", flush=True)
                xhs_process = subprocess.Popen(
                    [str(node), str(xhs_entry)],
                    cwd=xhs_entry.parent,
                    env=xhs_environment,
                )
                children.append(("小红书 MCP", xhs_process))

        if _url_ready(f"{BACKEND_URL}/api/v1/health"):
            print(f"[OK] 检测到后端已经运行：{BACKEND_URL}")
        else:
            from db.engine import get_database_engine

            print("正在检查并初始化数据库……", flush=True)
            get_database_engine().create_all()
            print("正在启动 TravelMind 后端……", flush=True)
            backend_process = subprocess.Popen(
                [sys.executable, "-m", "scripts.run_api"],
                cwd=PROJECT_ROOT,
            )
            children.append(("后端", backend_process))

        if _url_ready(FRONTEND_URL):
            print(f"[OK] 检测到前端已经运行：{FRONTEND_URL}")
        else:
            node = _find_node()
            vite = _vite_entry()
            print("正在启动 TravelMind 前端……")
            frontend_process = subprocess.Popen(
                [
                    str(node),
                    str(vite),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "5173",
                    "--strictPort",
                ],
                cwd=FRONTEND_ROOT,
            )
            children.append(("前端", frontend_process))

        _wait_until_ready(
            f"{BACKEND_URL}/api/v1/health",
            "后端",
            backend_process,
        )
        if settings.xhs_mcp_enabled:
            _wait_until_ready(xhs_health_url, "小红书 MCP", xhs_process, timeout=180)
        _wait_until_ready(FRONTEND_URL, "前端", frontend_process)

        print("\nTravelMind 已启动。")
        print(f"页面地址：{FRONTEND_URL}")
        print(f"接口文档：{BACKEND_URL}/docs")
        if settings.xhs_mcp_enabled:
            print(f"小红书 MCP：{settings.xhs_mcp_url}")
        print("按 Ctrl+C 可同时关闭本次启动的前后端服务。\n")
        if open_browser:
            webbrowser.open(FRONTEND_URL)

        while children:
            for label, process in children:
                exit_code = process.poll()
                if exit_code is not None:
                    raise RuntimeError(f"{label}意外退出，退出码：{exit_code}")
            time.sleep(0.5)
        return 0
    except KeyboardInterrupt:
        print("\n收到停止请求。")
        return 0
    except Exception as exc:
        print(f"\n启动失败：{exc}", file=sys.stderr)
        return 1
    finally:
        for label, process in reversed(children):
            _stop_process(process, label)


def main() -> int:
    """解析命令行参数并执行 main 的主流程。"""
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in {"utf-8", "utf8"}:
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr.encoding and sys.stderr.encoding.lower() not in {"utf-8", "utf8"}:
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="TravelMind 本地启动器")
    parser.add_argument("--cli", action="store_true", help="运行原来的命令行旅行助手")
    parser.add_argument("--no-browser", action="store_true", help="启动网页服务但不自动打开浏览器")
    args = parser.parse_args()
    if args.cli:
        run_cli()
        return 0
    return run_web(open_browser=not args.no_browser)


if __name__ == "__main__":
    raise SystemExit(main())
