"""提供 项目维护和命令行操作；本文件负责 `run_api` 相关实现。"""

import argparse

import uvicorn

from api.app import create_app


def main() -> int:
    """解析命令行参数并执行 run_api 的主流程。"""
    parser = argparse.ArgumentParser(description="Run TravelMind API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run(
        "api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        app_dir=".",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
