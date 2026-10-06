"""主协调、反馈、规划、工具执行和总结五类 Agent 节点。"""

from __future__ import annotations

from time import perf_counter
from collections.abc import Callable
from typing import Any

from multi_agent.executor import ToolExecutor
from multi_agent.planner import TravelRouter
from multi_agent.summarizer import ResponseGenerator
from memory.memory_manager import load_agent_state, save_agent_state, update_user_profile
from multi_agent.state import TravelGraphState
from schemas.agent_state import AgentState, ChatMessage
from schemas.itinerary import Itinerary
from schemas.route import RoutePlan, RouteResult
from schemas.tool import ToolResult
from schemas.travel_request import TravelRequest
from schemas.user_profile import ProfileExtraction
from tools.profile_tool import extract_profile_updates
from services.itinerary_renderer import render_itinerary_markdown
from services.memory_pipeline import MemoryPipeline
from utils.ids import new_request_id, new_trip_id


def _trace(state: TravelGraphState, node: str) -> list[str]:
    """在图状态中追加当前节点名称，形成可观测执行轨迹。"""
    return [*state.get("node_trace", []), node]


class CoordinatorAgent:
    """恢复会话、建立请求上下文并把工作交给下游节点。"""

    def __call__(self, state: TravelGraphState) -> dict[str, Any]:
        """执行 CoordinatorAgent 节点并返回本轮状态更新。"""
        agent_state = load_agent_state(state["session_id"], state["user_id"])
        agent_state.request_id = state.get("request_id") or new_request_id()
        agent_state.chat_history.append(ChatMessage(role="user", content=state["user_input"]))
        return {
            "request_id": agent_state.request_id,
            "agent_state": agent_state.model_dump(mode="json"),
            "current_node": "coordinator",
            "node_trace": _trace(state, "coordinator"),
            "errors": [],
        }


class FeedbackAgent:
    """识别当前旅行约束、长期偏好、长期记忆以及开始新旅行的反馈。"""

    def __init__(
        self,
        extractor: Callable[..., ProfileExtraction] | None = None,
        memory_pipeline: MemoryPipeline | None = None,
    ) -> None:
        """初始化 FeedbackAgent 及其运行依赖。"""
        self.extractor = extractor or extract_profile_updates
        self.memory_pipeline = memory_pipeline or MemoryPipeline()

    def __call__(self, state: TravelGraphState) -> dict[str, Any]:
        """执行 FeedbackAgent 节点并返回本轮状态更新。"""
        agent_state = AgentState.model_validate(state["agent_state"])
        updates = self.extractor(
            state["user_input"],
            current_profile=agent_state.user_profile,
            current_trip=agent_state.travel_request,
            chat_history=agent_state.chat_history[:-1],
        )
        if updates.start_new_trip:
            agent_state.trip_id = new_trip_id()
            agent_state.travel_request = TravelRequest()
            agent_state.current_itinerary = None
            agent_state.structured_itinerary = None
            agent_state.budget_plan = None
            agent_state.weather_info = None
            agent_state.exchange_info = None
        agent_state.user_profile = update_user_profile(
            updates.profile_updates,
            agent_state.user_id,
            clear_fields=updates.clear_profile_fields,
            remove_items=updates.remove_profile_items,
        )
        agent_state.travel_request = agent_state.travel_request.apply_update(
            updates.trip_updates,
            clear_fields=updates.clear_trip_fields,
            remove_items=updates.remove_trip_items,
        )
        try:
            memory_result = self.memory_pipeline.ingest_candidates(
                updates.memory_candidates,
                user_id=agent_state.user_id,
                session_id=agent_state.session_id,
                trip_id=agent_state.trip_id,
            )
        except Exception:
            memory_result = None
        memory_summary = (
            {
                "created": memory_result.created,
                "merged": memory_result.merged,
                "deferred": memory_result.deferred,
                "rejected": memory_result.rejected,
                "errors": memory_result.errors,
            }
            if memory_result is not None
            else {}
        )
        agent_state.last_memory_result = memory_summary
        return {
            "agent_state": agent_state.model_dump(mode="json"),
            "current_node": "feedback",
            "node_trace": _trace(state, "feedback"),
        }


class PlannerAgent:
    """把用户目标分解成有依赖关系的工具执行计划。"""

    def __init__(self, router: TravelRouter | None = None) -> None:
        """初始化 PlannerAgent 及其运行依赖。"""
        self.router = router or TravelRouter()

    def __call__(self, state: TravelGraphState) -> dict[str, Any]:
        """执行 PlannerAgent 节点并返回本轮状态更新。"""
        agent_state = AgentState.model_validate(state["agent_state"])
        plan = self.router.route(state["user_input"], agent_state)
        agent_state.route_confidence = plan.confidence
        agent_state.last_intent = plan.primary.intent
        agent_state.last_tool_name = plan.primary.tool_name
        agent_state.last_tool_names = [step.tool_name for step in plan.steps]
        return {
            "agent_state": agent_state.model_dump(mode="json"),
            "route_plan": plan.model_dump(mode="json"),
            "needs_clarification": plan.needs_clarification,
            "clarification_question": plan.clarification_question,
            "current_node": "planner",
            "node_trace": _trace(state, "planner"),
        }


class ToolExecutionAgent:
    """按依赖顺序调用白名单工具，并统一记录结果和耗时。"""

    def __init__(self, executor: ToolExecutor | None = None) -> None:
        """初始化 ToolExecutionAgent 及其运行依赖。"""
        self.executor = executor or ToolExecutor()

    def __call__(self, state: TravelGraphState) -> dict[str, Any]:
        """执行 ToolExecutionAgent 节点并返回本轮状态更新。"""
        agent_state = AgentState.model_validate(state["agent_state"])
        plan = RoutePlan.model_validate(state["route_plan"])
        started = perf_counter()

        def update_after_each(route: RouteResult, result: ToolResult) -> None:
            """在每个工具步骤结束后同步最新 AgentState。"""
            agent_state.current_stage = route.stage
            if not result.success:
                agent_state.last_error = result.error.code if result.error else "tool_error"
                return
            agent_state.last_error = None
            if route.tool_name in {"plan_itinerary", "refine_itinerary"}:
                itinerary = Itinerary.model_validate(result.data)
                agent_state.structured_itinerary = itinerary
                agent_state.current_itinerary = render_itinerary_markdown(itinerary)
            elif route.tool_name == "estimate_budget":
                agent_state.budget_plan = str(result.data)
            elif route.tool_name == "check_weather":
                agent_state.weather_info = {"result": result.data, "metadata": result.metadata}
            elif route.tool_name == "convert_currency":
                agent_state.exchange_info = {"result": result.data, "metadata": result.metadata}

        completed = self.executor.execute_plan(
            plan,
            state["user_input"],
            agent_state,
            after_each=update_after_each,
        )
        serialized = []
        errors = list(state.get("errors", []))
        for route, result in completed:
            item = {
                "route": route.model_dump(mode="json"),
                "result": result.model_dump(mode="json"),
            }
            serialized.append(item)
            if not result.success:
                errors.append(
                    {
                        "node": "tool_executor",
                        "tool": route.tool_name,
                        "code": result.error.code if result.error else "tool_error",
                    }
                )
        return {
            "agent_state": agent_state.model_dump(mode="json"),
            "tool_results": serialized,
            "current_node": "tool_executor",
            "node_trace": _trace(state, "tool_executor"),
            "errors": errors,
            "execution_elapsed_seconds": round(perf_counter() - started, 3),
        }


class SummarizerAgent:
    """把多个工具结果合并成最终回复，并保存会话状态。"""

    def __init__(self, response_generator: ResponseGenerator | None = None) -> None:
        """初始化 SummarizerAgent 及其运行依赖。"""
        self.response_generator = response_generator or ResponseGenerator()

    def __call__(self, state: TravelGraphState) -> dict[str, Any]:
        """执行 SummarizerAgent 节点并返回本轮状态更新。"""
        agent_state = AgentState.model_validate(state["agent_state"])
        if state.get("needs_clarification"):
            response = state.get("clarification_question") or "请补充更明确的旅行需求。"
        else:
            completed = [
                (
                    RouteResult.model_validate(item["route"]),
                    ToolResult.model_validate(item["result"]),
                )
                for item in state.get("tool_results", [])
            ]
            response = self.response_generator.generate_many(
                completed,
                user_input=state["user_input"],
            )
        agent_state.chat_history.append(ChatMessage(role="assistant", content=response))
        save_agent_state(agent_state)
        return {
            "agent_state": agent_state.model_dump(mode="json"),
            "response": response,
            "current_node": "summarizer",
            "node_trace": _trace(state, "summarizer"),
        }
