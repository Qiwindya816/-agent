"""LangGraph 节点间共享的原始状态。"""

from __future__ import annotations

from typing import Any, TypedDict


class TravelGraphState(TypedDict, total=False):
    """只保存节点间需要共享和持久化的数据，不保存格式化 Prompt。"""

    user_id: str  # 用户 ID
    session_id: str  # 会话 ID
    request_id: str  # 请求 ID
    user_input: str  # 用户输入
    agent_state: dict[str, Any]  # Agent 状态
    route_plan: dict[str, Any]  # 工具计划
    tool_results: list[dict[str, Any]]  # 工具结果
    response: str  # 最终回复
    needs_clarification: bool  # 是否需要澄清
    clarification_question: str | None  # 澄清问题
    current_node: str  # 当前节点
    node_trace: list[str]  # 节点轨迹
    errors: list[dict[str, Any]]  # 错误
    execution_elapsed_seconds: float  # 执行耗时秒
