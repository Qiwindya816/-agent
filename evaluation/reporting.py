"""提供 离线评测数据、指标与报告；本文件负责 `reporting` 相关实现。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_reports(report: dict[str, Any], json_path: Path) -> tuple[Path, Path]:
    """写出机器可读 JSON 和简洁的 Markdown 评测报告。"""
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = json_path.with_suffix(".md")
    lines = ["# TravelMind 评测报告", "", f"- 生成时间：{report['created_at']}", f"- 总体状态：{report['status']}", ""]
    for section_name in ("rag", "itinerary", "trip_feedback", "memory", "memory_privacy"):
        section = report.get(section_name)
        if not section:
            continue
        lines.extend([f"## {section_name}", "", "```json", json.dumps(section.get("macro_metrics") or section.get("metrics") or section, ensure_ascii=False, indent=2), "```", ""])
    if report.get("warnings"):
        lines.extend(["## 注意事项", ""] + [f"- {item}" for item in report["warnings"]] + [""])
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, markdown_path
