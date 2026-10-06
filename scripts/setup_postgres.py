"""提供 项目维护和命令行操作；本文件负责 `setup_postgres` 相关实现。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from sqlalchemy.engine import make_url

from config.settings import PROJECT_ROOT, get_settings


CONTAINER_NAME = "travelmind-postgres"
VOLUME_NAME = "travelmind_pgdata"
IMAGE = "pgvector/pgvector:pg16"


def _docker_executable() -> str:
    """定位当前系统可用的 Docker 命令。"""
    discovered = shutil.which("docker")
    if discovered:
        return discovered
    windows_path = Path(r"C:\Program Files\Docker\Docker\resources\bin\docker.exe")
    if windows_path.is_file():
        return str(windows_path)
    raise RuntimeError("未找到 Docker CLI，请确认 Docker Desktop 已安装。")


def _run(docker: str, *arguments: str, capture: bool = False) -> str:
    """执行外部命令并在失败时返回便于诊断的输出。"""
    result = subprocess.run(
        [docker, *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        text=True,
        capture_output=capture,
    )
    return result.stdout.strip() if capture else ""


def main() -> int:
    """解析命令行参数并执行 setup_postgres 的主流程。"""
    settings = get_settings()
    url = make_url(settings.database_url)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("DATABASE_URL 必须使用 postgresql+psycopg://。")
    if not url.username or url.password is None or not url.database:
        raise RuntimeError("DATABASE_URL 缺少数据库用户名、密码或数据库名。")
    if (url.host or "127.0.0.1") not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("该脚本只用于配置本机 PostgreSQL，不会修改远程数据库。")

    docker = _docker_executable()
    host_port = str(url.port or 5432)
    existing = _run(
        docker,
        "ps",
        "-a",
        "--filter",
        f"name=^/{CONTAINER_NAME}$",
        "--format",
        "{{.Names}}",
        capture=True,
    )
    if existing == CONTAINER_NAME:
        print(f"检测到已有容器 {CONTAINER_NAME}，正在启动……", flush=True)
        _run(docker, "start", CONTAINER_NAME)
    else:
        print(f"正在拉取并创建 {IMAGE}……", flush=True)
        _run(
            docker,
            "run",
            "--name",
            CONTAINER_NAME,
            "--restart",
            "unless-stopped",
            "-e",
            f"POSTGRES_USER={url.username}",
            "-e",
            f"POSTGRES_PASSWORD={url.password}",
            "-e",
            f"POSTGRES_DB={url.database}",
            "-p",
            f"{host_port}:5432",
            "-v",
            f"{VOLUME_NAME}:/var/lib/postgresql/data",
            "-d",
            IMAGE,
        )

    print("正在等待 PostgreSQL 接受连接……", flush=True)
    for _ in range(40):
        ready = subprocess.run(
            [
                docker,
                "exec",
                CONTAINER_NAME,
                "pg_isready",
                "-U",
                url.username,
                "-d",
                url.database,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if ready.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("PostgreSQL 在 40 秒内未就绪，请检查 Docker Desktop 日志。")

    print("正在启用 pgvector 扩展……", flush=True)
    for _ in range(20):
        extension = subprocess.run(
            [
                docker,
                "exec",
                CONTAINER_NAME,
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                url.username,
                "-d",
                url.database,
                "-c",
                "CREATE EXTENSION IF NOT EXISTS vector;",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if extension.returncode == 0:
            print(extension.stdout.strip())
            break
        time.sleep(1)
    else:
        raise RuntimeError("数据库已启动，但无法启用 pgvector 扩展。")

    print("正在执行 Alembic migration……", flush=True)
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT,
        check=True,
        env=os.environ.copy(),
    )
    print("PostgreSQL + pgvector 配置完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
