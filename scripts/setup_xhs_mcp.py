"""提供 项目维护和命令行操作；本文件负责 `setup_xhs_mcp` 相关实现。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = PROJECT_ROOT / "integrations" / "xhs-mcp-runtime"
DOWNLOAD_ROOT = RUNTIME_ROOT / ".downloads"


def _executable(*names: str) -> str:
    """定位指定外部程序的可执行文件。"""
    for name in names:
        value = shutil.which(name)
        if value:
            return value
    raise RuntimeError(f"未找到可执行程序：{', '.join(names)}")


def _download_with_resume(url: str, target: Path, attempts: int = 8) -> None:
    """下载文件，并在已有部分文件时尝试断点续传。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, attempts + 1):
        existing = target.stat().st_size if target.exists() else 0
        request = urllib.request.Request(url, headers={"User-Agent": "TravelMind-XHS-Setup/1.0"})
        if existing:
            request.add_header("Range", f"bytes={existing}-")
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                append = existing > 0 and response.status == 206
                mode = "ab" if append else "wb"
                with target.open(mode) as output:
                    while block := response.read(1024 * 1024):
                        output.write(block)
            return
        except Exception as exc:  # noqa: BLE001 - 重试范围需要包含网络和套接字异常
            if attempt == attempts:
                raise RuntimeError(f"下载依赖失败：{url}\n{exc}") from exc
            print(f"下载暂时中断，正在续传（{attempt}/{attempts}）……", flush=True)
            time.sleep(min(attempt * 2, 10))


def _safe_extract(archive: Path, destination: Path) -> None:
    """校验归档成员路径后安全解压文件。"""
    destination = destination.resolve()
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            resolved = (destination / member.name).resolve()
            if destination not in resolved.parents and resolved != destination:
                raise RuntimeError(f"压缩包包含不安全路径：{member.name}")
        bundle.extractall(destination, filter="data")


def main() -> int:
    """解析命令行参数并执行 setup_xhs_mcp 的主流程。"""
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in {"utf-8", "utf8"}:
        sys.stdout.reconfigure(encoding="utf-8")
    npm = _executable("npm.cmd", "npm")
    node = _executable("node.exe", "node")
    print("正在安装固定版本 @sillyl12324/xhs-mcp（跳过非必要写作/制图依赖脚本）……")
    subprocess.run([npm, "install", "--ignore-scripts"], cwd=RUNTIME_ROOT, check=True)

    sqlite_root = RUNTIME_ROOT / "node_modules" / "better-sqlite3"
    sqlite_package = json.loads((sqlite_root / "package.json").read_text(encoding="utf-8"))
    version = sqlite_package["version"]
    abi = subprocess.check_output(
        [node, "-p", "process.versions.modules"], cwd=RUNTIME_ROOT, text=True
    ).strip()
    arch = subprocess.check_output([node, "-p", "process.arch"], text=True).strip()
    platform_name = "win32" if os.name == "nt" else sys.platform
    filename = f"better-sqlite3-v{version}-node-v{abi}-{platform_name}-{arch}.tar.gz"
    binary = sqlite_root / "build" / "Release" / "better_sqlite3.node"
    if not binary.is_file():
        if platform_name != "win32":
            raise RuntimeError("当前自动安装脚本仅处理 Windows 原生 SQLite 预编译包。")
        archive = DOWNLOAD_ROOT / filename
        url = f"https://github.com/WiseLibs/better-sqlite3/releases/download/v{version}/{filename}"
        print("正在下载 SQLite 原生运行库；网络较慢时会自动断点续传……")
        _download_with_resume(url, archive)
        _safe_extract(archive, sqlite_root)

    subprocess.run([node, "-e", "require('better-sqlite3'); console.log('SQLite runtime OK')"], cwd=RUNTIME_ROOT, check=True)

    browser_candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    ]
    if os.name == "nt" and not any(path.is_file() for path in browser_candidates):
        print("警告：未检测到 Chrome 或 Edge；登录/采集前需安装其中一个浏览器。")
    print("小红书 MCP 运行环境配置完成。可运行：python main.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
