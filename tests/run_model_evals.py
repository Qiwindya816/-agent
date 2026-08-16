"""运行 TravelMind 结构化 LLM 评测并输出 JSON 报告。"""

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

from prompts.profile_prompt import PROFILE_SYSTEM_PROMPT, build_profile_prompt  # noqa: E402
from prompts.router_prompt import ROUTER_SYSTEM_PROMPT, build_router_prompt  # noqa: E402
from prompts.weather_prompt import WEATHER_QUERY_SYSTEM_PROMPT, build_weather_query_prompt  # noqa: E402
from schemas.agent_state import AgentState  # noqa: E402
from services.llm_service import LLMService  # noqa: E402


DEFAULT_CASES_PATH = PROJECT_ROOT / "tests" / "model_eval_cases.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "outputs" / "model_eval_report.json"
STRUCTURED_COMPONENTS = {"router", "profile", "weather"}


def _matches_value(actual: Any, expected: Any) -> bool:
    """判断实际值是否满足精确值或列表包含关系。"""
    if isinstance(expected, list):
        return isinstance(actual, list) and all(item in actual for item in expected)
    return actual == expected


def _score_case(case: dict[str, Any], actual: dict[str, Any]) -> tuple[bool, list[str]]:
    """根据样例中的期望字段检查模型结构化输出。"""
    failures: list[str] = []

    for field, expected in case.get("expected", {}).items():
        value = actual.get(field)
        if not _matches_value(value, expected):
            failures.append(f"{field}: expected {expected!r}, got {value!r}")

    for field, expected in case.get("expected_contains", {}).items():
        value = actual.get(field)
        if not _matches_value(value, expected):
            failures.append(f"{field}: expected to contain {expected!r}, got {value!r}")

    for field in case.get("expected_empty", []):
        value = actual.get(field)
        if value not in (None, "", []):
            failures.append(f"{field}: expected empty, got {value!r}")

    return not failures, failures


def _run_structured_case(service: LLMService, case: dict[str, Any]) -> dict[str, Any]:
    """调用对应提示词运行一条路由、画像或天气参数评测。"""
    component = case["component"]
    user_input = case["input"]

    if component == "router":
        state = AgentState(
            current_itinerary="已有行程" if case.get("context", {}).get("has_itinerary") else None
        )
        result = service.generate_json(
            build_router_prompt(user_input, state),
            system_prompt=ROUTER_SYSTEM_PROMPT,
            temperature=0,
        )
        steps = result.get("steps")
        if isinstance(steps, list) and steps and isinstance(steps[0], dict):
            return {
                **result,
                **steps[0],
                "tool_names": [step.get("tool_name") for step in steps if isinstance(step, dict)],
            }
        return result

    if component == "profile":
        result = service.generate_json(
            build_profile_prompt(user_input),
            system_prompt=PROFILE_SYSTEM_PROMPT,
            temperature=0,
        )
        if isinstance(result.get("profile_updates"), dict) or isinstance(result.get("trip_updates"), dict):
            return {
                **result,
                **dict(result.get("profile_updates") or {}),
                **dict(result.get("trip_updates") or {}),
            }
        return result

    if component == "weather":
        return service.generate_json(
            build_weather_query_prompt(user_input),
            system_prompt=WEATHER_QUERY_SYSTEM_PROMPT,
            temperature=0,
        )

    raise ValueError(f"不支持自动运行的组件：{component}")


def run_evaluations(
    cases: list[dict[str, Any]],
    component: str = "all",
    limit: int | None = None,
) -> dict[str, Any]:
    """运行选定结构化样例并汇总通过率、失败原因和原始输出。"""
    selected = [
        case
        for case in cases
        if case.get("component") in STRUCTURED_COMPONENTS
        and (component == "all" or case.get("component") == component)
    ]
    if limit is not None:
        selected = selected[:limit]

    service = LLMService()
    results: list[dict[str, Any]] = []

    for case in selected:
        try:
            actual = _run_structured_case(service, case)
            passed, failures = _score_case(case, actual)
            results.append(
                {
                    "id": case["id"],
                    "component": case["component"],
                    "passed": passed,
                    "focus": case.get("focus"),
                    "failures": failures,
                    "actual": actual,
                }
            )
        except Exception as exc:
            results.append(
                {
                    "id": case["id"],
                    "component": case["component"],
                    "passed": False,
                    "focus": case.get("focus"),
                    "failures": [f"{type(exc).__name__}: {exc}"],
                    "actual": None,
                }
            )

    passed_count = sum(result["passed"] for result in results)
    by_component: dict[str, dict[str, int | float]] = {}
    for name in sorted(STRUCTURED_COMPONENTS):
        component_results = [result for result in results if result["component"] == name]
        if not component_results:
            continue
        component_passed = sum(result["passed"] for result in component_results)
        by_component[name] = {
            "total": len(component_results),
            "passed": component_passed,
            "pass_rate": round(component_passed / len(component_results), 4),
        }

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": service.settings.deepseek_model,
        "total": len(results),
        "passed": passed_count,
        "pass_rate": round(passed_count / len(results), 4) if results else 0,
        "by_component": by_component,
        "results": results,
    }


def main() -> None:
    """解析命令行参数，运行评测并写入报告文件。"""
    parser = argparse.ArgumentParser(description="运行 TravelMind 的结构化 LLM 评测。")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH, help="评测样例 JSON 文件。")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH, help="评测报告输出路径。")
    parser.add_argument(
        "--component",
        choices=["all", *sorted(STRUCTURED_COMPONENTS)],
        default="all",
        help="只运行指定组件。",
    )
    parser.add_argument("--limit", type=int, default=None, help="最多运行多少条样例。")
    args = parser.parse_args()

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    report = run_evaluations(cases, component=args.component, limit=args.limit)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"模型：{report['model']}")
    print(f"通过：{report['passed']}/{report['total']} ({report['pass_rate']:.1%})")
    print(f"报告：{args.report}")


if __name__ == "__main__":
    main()
