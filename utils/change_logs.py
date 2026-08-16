from pathlib import Path
from datetime import datetime
import json
import hashlib


# 项目根目录：utils/change_tracker.py 的上一级的上一级
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 日志目录
LOG_DIR = PROJECT_ROOT / "logs"
SNAPSHOT_FILE = LOG_DIR / "file_snapshot.json"
CHANGE_LOG_FILE = LOG_DIR / "file_changes.md"


# 不需要追踪的文件夹和文件
IGNORE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".idea",
    ".vscode",
    "logs",       # 避免 tracker 自己生成的日志不断触发变化
    "outputs",
}

IGNORE_FILES = {
    ".env",
}


def calculate_file_hash(file_path: Path) -> str:
    """
    计算文件 hash，用来判断文件内容是否真的改变。
    """
    hash_md5 = hashlib.md5()

    try:
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
    except Exception:
        return ""

    return hash_md5.hexdigest()


def should_ignore(path: Path) -> bool:
    """
    判断某个文件或目录是否应该被忽略。
    """
    relative_parts = path.relative_to(PROJECT_ROOT).parts

    for part in relative_parts:
        if part in IGNORE_DIRS:
            return True

    if path.name in IGNORE_FILES:
        return True

    return False


def scan_project_files() -> dict:
    """
    扫描当前项目文件，返回文件快照。
    """
    snapshot = {}

    for file_path in PROJECT_ROOT.rglob("*"):
        if file_path.is_file() and not should_ignore(file_path):
            relative_path = str(file_path.relative_to(PROJECT_ROOT)).replace("\\", "/")

            stat = file_path.stat()

            snapshot[relative_path] = {
                "size": stat.st_size,
                "modified_time": stat.st_mtime,
                "hash": calculate_file_hash(file_path),
            }

    return snapshot


def load_previous_snapshot() -> dict:
    """
    读取上一次的文件快照。
    """
    if not SNAPSHOT_FILE.exists():
        return {}

    try:
        with SNAPSHOT_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_snapshot(snapshot: dict) -> None:
    """
    保存当前文件快照。
    """
    LOG_DIR.mkdir(exist_ok=True)

    with SNAPSHOT_FILE.open("w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def compare_snapshots(old: dict, new: dict) -> dict:
    """
    对比旧快照和新快照，找出新增、修改、删除文件。
    """
    old_files = set(old.keys())
    new_files = set(new.keys())

    added = sorted(new_files - old_files)
    deleted = sorted(old_files - new_files)

    modified = []

    for file_path in old_files & new_files:
        old_info = old[file_path]
        new_info = new[file_path]

        # 用 hash 判断内容是否改变，比只看修改时间更准确
        if old_info.get("hash") != new_info.get("hash"):
            modified.append(file_path)

    return {
        "added": added,
        "modified": sorted(modified),
        "deleted": deleted,
    }


def write_change_log(changes: dict) -> None:
    """
    将文件变化写入 Markdown 日志。
    """
    LOG_DIR.mkdir(exist_ok=True)

    has_changes = any(changes[key] for key in ["added", "modified", "deleted"])

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not CHANGE_LOG_FILE.exists():
        CHANGE_LOG_FILE.write_text("# File Change Log\n\n", encoding="utf-8")

    with CHANGE_LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"## {timestamp}\n\n")

        if not has_changes:
            f.write("No file changes detected.\n\n")
            return

        if changes["added"]:
            f.write("### Added\n")
            for file_path in changes["added"]:
                f.write(f"- {file_path}\n")
            f.write("\n")

        if changes["modified"]:
            f.write("### Modified\n")
            for file_path in changes["modified"]:
                f.write(f"- {file_path}\n")
            f.write("\n")

        if changes["deleted"]:
            f.write("### Deleted\n")
            for file_path in changes["deleted"]:
                f.write(f"- {file_path}\n")
            f.write("\n")


def track_changes() -> dict:
    """
    主函数：扫描项目、对比变化、写入日志、更新快照。
    """
    old_snapshot = load_previous_snapshot()
    new_snapshot = scan_project_files()

    changes = compare_snapshots(old_snapshot, new_snapshot)

    write_change_log(changes)
    save_snapshot(new_snapshot)

    return changes


if __name__ == "__main__":
    changes = track_changes()

    print("File change tracking completed.")
    print("Added:", changes["added"])
    print("Modified:", changes["modified"])
    print("Deleted:", changes["deleted"])
