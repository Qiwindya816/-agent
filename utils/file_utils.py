from pathlib import Path


def ensure_dir(path: Path) -> Path:
    """确保目录及其父目录存在，并返回原路径对象。"""
    path.mkdir(parents=True, exist_ok=True)
    return path
