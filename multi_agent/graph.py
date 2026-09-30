"""TravelMind 五角色 LangGraph 拓扑。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from services.checkpoints import build_checkpointer
from langgraph.graph import END, START, StateGraph

from multi_agent.executor import ToolExecutor
from multi_agent.planner import TravelRouter
from multi_agent.summarizer import ResponseGenerator
from multi_agent.nodes import (
    CoordinatorAgent,
    FeedbackAgent,
    PlannerAgent,
    SummarizerAgent,
    ToolExecutionAgent,
)
from multi_agent.state import TravelGraphState
from schemas.user_profile import ProfileExtraction


def _after_planner(state: TravelGraphState) -> str:
    return "summarizer" if state.get("needs_clarification") else "tool_executor"


def build_travel_graph(
    *,
    router: TravelRouter | None = None,
    executor: ToolExecutor | None = None,
    response_generator: ResponseGenerator | None = None,
    profile_extractor: Callable[..., ProfileExtraction] | None = None,
    checkpointer: Any | None = None,
):
    """构建可注入依赖和 Checkpointer 的五节点工作流。"""

    builder = StateGraph(TravelGraphState)
    builder.add_node("coordinator", CoordinatorAgent())
    builder.add_node("feedback", FeedbackAgent(profile_extractor))
    builder.add_node("planner", PlannerAgent(router))
    builder.add_node("tool_executor", ToolExecutionAgent(executor))
    builder.add_node("summarizer", SummarizerAgent(response_generator))

    builder.add_edge(START, "coordinator")
    builder.add_edge("coordinator", "feedback")
    builder.add_edge("feedback", "planner")
    builder.add_conditional_edges(
        "planner",
        _after_planner,
        {"tool_executor": "tool_executor", "summarizer": "summarizer"},
    )
    builder.add_edge("tool_executor", "summarizer")
    builder.add_edge("summarizer", END)
    return builder.compile(checkpointer=checkpointer or build_checkpointer())
