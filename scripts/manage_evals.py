"""提供 项目维护和命令行操作；本文件负责 `manage_evals` 相关实现。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings  # noqa: E402
from db.engine import DatabaseEngine  # noqa: E402
from evaluation.itinerary import evaluate_itineraries, evaluate_trip_feedback  # noqa: E402
from evaluation.memory import evaluate_memory_cases, evaluate_memory_privacy  # noqa: E402
from evaluation.rag import evaluate_rag_cases  # noqa: E402
from evaluation.reporting import write_reports  # noqa: E402
from services.embedding_service import EmbeddingService  # noqa: E402
from services.rag_retrieval import RagRetrievalService  # noqa: E402


DEFAULT_RAG_CASES = PROJECT_ROOT / "evaluation" / "datasets" / "rag_golden.json"
DEFAULT_ITINERARY_CASES = PROJECT_ROOT / "evaluation" / "datasets" / "itinerary_cases.json"
DEFAULT_MEMORY_CASES = PROJECT_ROOT / "evaluation" / "datasets" / "memory_cases.json"
DEFAULT_REPORT = PROJECT_ROOT / "outputs" / "evaluations" / "baseline.json"


def _load_cases(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """加载cases并返回符合当前作用域的结果。"""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload, {}
    return list(payload.get("cases") or []), dict(payload.get("metadata") or {})


def run_suite(args: argparse.Namespace) -> dict[str, Any]:
    """执行 `run_suite` 对应的数据和流程，返回该步骤的处理结果。"""
    settings = get_settings()
    database = DatabaseEngine(settings.database_url)
    warnings: list[str] = []
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pass",
        "database_backend": "postgresql" if database.url.startswith("postgresql") else "sqlite",
        "warnings": warnings,
    }
    selected = set(args.sections.split(",")) if args.sections != "all" else {"rag", "itinerary", "memory"}

    if "rag" in selected:
        cases, metadata = _load_cases(args.rag_cases)
        if metadata.get("calibration_status") != "approved":
            warnings.append("RAG 黄金集尚未标记为 approved；当前分数只能作为试运行基线。")
        embedding = None if args.no_embedding else EmbeddingService()
        report["rag"] = evaluate_rag_cases(
            RagRetrievalService(database, embedding),
            cases,
            default_user_id=args.user_id,
            k=args.k,
        )
        report["rag"]["dataset_metadata"] = metadata

    if "itinerary" in selected:
        cases, metadata = _load_cases(args.itinerary_cases)
        report["itinerary"] = evaluate_itineraries(cases)
        report["itinerary"]["dataset_metadata"] = metadata
        report["trip_feedback"] = evaluate_trip_feedback(database, user_id=args.user_id if args.user_scope else None)
        if report["trip_feedback"]["feedback_count"] == 0:
            warnings.append("数据库中暂无行程反馈；接受率和真实用户修改次数尚不能形成基线。")

    if "memory" in selected:
        cases, metadata = _load_cases(args.memory_cases)
        report["memory"] = evaluate_memory_cases(cases)
        report["memory"]["dataset_metadata"] = metadata
        report["memory_privacy"] = evaluate_memory_privacy(database)
        if report["memory_privacy"]["checked_items"] == 0:
            warnings.append("数据库中暂无长期记忆；隐私结果目前只由自动化隔离测试支撑。")

    failures = []
    rag_metrics = report.get("rag", {}).get("macro_metrics", {})
    if rag_metrics and rag_metrics.get(f"recall@{args.k}", 0) < args.min_rag_recall:
        failures.append(f"RAG Recall@{args.k} 低于 {args.min_rag_recall:.2f}")
    itinerary_metrics = report.get("itinerary", {}).get("metrics", {})
    if itinerary_metrics and any(itinerary_metrics.get(name, 0) > 0 for name in ("time_conflict_rate", "budget_overrun_rate")):
        failures.append("行程测试集存在时间冲突或预算超限")
    if report.get("memory_privacy", {}).get("privacy_leak_count", 0) > 0:
        failures.append("Memory 跨用户隐私检查发现泄漏")
    report["failures"] = failures
    report["status"] = "fail" if failures else "pass"
    database.dispose()
    return report


def main() -> int:
    """解析命令行参数并执行 manage_evals 的主流程。"""
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in {"utf-8", "utf8"}:
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="运行 TravelMind 阶段 9 评测套件")
    parser.add_argument("--sections", default="all", help="all 或 rag,itinerary,memory 的组合")
    parser.add_argument("--rag-cases", type=Path, default=DEFAULT_RAG_CASES)
    parser.add_argument("--itinerary-cases", type=Path, default=DEFAULT_ITINERARY_CASES)
    parser.add_argument("--memory-cases", type=Path, default=DEFAULT_MEMORY_CASES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--user-id", default=get_settings().xhs_pilot_user_id)
    parser.add_argument("--user-scope", action="store_true", help="行程反馈指标只统计 --user-id")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--min-rag-recall", type=float, default=0.6)
    parser.add_argument("--no-embedding", action="store_true", help="仅测关键词/模板等非向量召回")
    args = parser.parse_args()

    report = run_suite(args)
    json_path, markdown_path = write_reports(report, args.report)
    print(json.dumps({
        "status": report["status"],
        "rag": report.get("rag", {}).get("macro_metrics"),
        "itinerary": report.get("itinerary", {}).get("metrics"),
        "memory": report.get("memory", {}).get("metrics"),
        "memory_privacy": report.get("memory_privacy"),
        "warnings": report["warnings"],
        "report_json": str(json_path),
        "report_markdown": str(markdown_path),
    }, ensure_ascii=False, indent=2))
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
