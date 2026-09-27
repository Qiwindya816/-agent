"""LangGraph 节点间共享的原始状态。"""

from __future__ import annotations

from typing import Any, TypedDict


class TravelGraphState(TypedDict, total=False):
    """只保存节点间需要共享和持久化的数据，不保存格式化 Prompt。"""

    user_id: str
    session_id: str
    request_id: str
    user_input: str
    agent_state: dict[str, Any]
    route_plan: dict[str, Any]
    tool_results: list[dict[str, Any]]
    response: str
    needs_clarification: bool
    clarification_question: str | None
    current_node: str
    node_trace: list[str]
    errors: list[dict[str, Any]]
    execution_elapsed_seconds: float
