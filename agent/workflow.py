"""TravelMind 主工作流：身份恢复、记忆更新、任务规划、工具执行和版本化导出。"""

from time import perf_counter

from agent.executor import ToolExecutor
from agent.response_generator import ResponseGenerator
from agent.router import TravelRouter
from memory.memory_manager import load_agent_state, save_agent_state, update_user_profile
from schemas.agent_state import AgentState, ChatMessage
from schemas.route import RouteResult
from schemas.travel_request import TravelRequest
from schemas.tool import ToolResult
from services.export_service import ExportService
from tools.profile_tool import extract_profile_updates
from utils.ids import new_request_id, new_session_id, new_trip_id, validate_user_id
from utils.logger import get_logger


class TravelWorkflow:
    """协调一名用户在一个会话中的完整 Agent 处理流程。"""

    def __init__(
        self,
        user_id: str = "default_user",
        session_id: str | None = None,
        router: TravelRouter | None = None,
        executor: ToolExecutor | None = None,
        response_generator: ResponseGenerator | None = None,
        export_service: ExportService | None = None,
    ) -> None:
        """绑定登录用户和会话，并初始化可替换的工作流组件。"""
        self.user_id = validate_user_id(user_id)
        self.session_id = session_id or ("default_session" if user_id == "default_user" else new_session_id())
        self.router = router or TravelRouter()
        self.executor = executor or ToolExecutor()
        self.response_generator = response_generator or ResponseGenerator()
        self.export_service = export_service or ExportService()
        self.logger = get_logger(__name__)

        # 构造时立即创建用户、会话和旅行存档，确保即使尚未提问，登录 ID 也已保存。
        state = load_agent_state(self.session_id, self.user_id)
        save_agent_state(state)

    def run(self, user_input: str) -> str:
        """处理一轮输入，可顺序执行多个工具，并保存本轮与完整方案的历史版本。"""
        request_id = new_request_id()
        started = perf_counter()
        state = load_agent_state(self.session_id, self.user_id)
        state.request_id = request_id
        state.chat_history.append(ChatMessage(role="user", content=user_input))

        try:
            updates = extract_profile_updates(
                user_input,
                current_profile=state.user_profile,
                current_trip=state.travel_request,
                chat_history=state.chat_history[:-1],
            )
            if updates.start_new_trip:
                state.trip_id = new_trip_id()
                state.travel_request = TravelRequest()
                state.current_itinerary = None
                state.budget_plan = None
                state.weather_info = None
                state.exchange_info = None
            state.user_profile = update_user_profile(
                updates.profile_updates,
                state.user_id,
                clear_fields=updates.clear_profile_fields,
                remove_items=updates.remove_profile_items,
            )
            state.travel_request = state.travel_request.apply_update(
                updates.trip_updates,
                clear_fields=updates.clear_trip_fields,
                remove_items=updates.remove_trip_items,
            )

            plan = self.router.route(user_input, state)
            state.route_confidence = plan.confidence
            state.last_intent = plan.primary.intent
            state.last_tool_name = plan.primary.tool_name
            state.last_tool_names = [step.tool_name for step in plan.steps]

            if plan.needs_clarification:
                response = plan.clarification_question or "请补充更明确的旅行需求。"
                self._persist_response(state, response)
                self._log_completion(state, [], started)
                return response

            results = self.executor.execute_plan(
                plan,
                user_input,
                state,
                after_each=lambda route, result: self._update_state_from_result(state, route, result),
            )
            response = self.response_generator.generate_many(results)
            self._persist_response(state, response)
            self._log_completion(state, results, started)
            return response
        except Exception as exc:
            state.last_error = type(exc).__name__
            save_agent_state(state)
            self.logger.exception("request_failed", extra={"request_id": request_id})
            return "抱歉，本次请求处理失败。技术错误已记录到日志中，请稍后重试。"

    def _persist_response(self, state: AgentState, response: str) -> None:
        """保存聊天记录、本轮独立回答以及可追溯的完整方案版本。"""
        state.chat_history.append(ChatMessage(role="assistant", content=response))
        self.export_service.save_request_response(state, response)
        self.export_service.save_versioned_snapshot(state)
        save_agent_state(state)

    def _log_completion(
        self,
        state: AgentState,
        results: list[tuple[RouteResult, ToolResult]],
        started: float,
    ) -> None:
        """记录本轮多工具列表、总体成功状态、置信度和执行耗时。"""
        self.logger.info(
            "request_completed",
            extra={
                "request_id": state.request_id,
                "tool_names": state.last_tool_names,
                "success": all(result.success for _, result in results) if results else True,
                "route_confidence": state.route_confidence,
                "elapsed_time": round(perf_counter() - started, 3),
            },
        )

    def _update_state_from_result(self, state: AgentState, route: RouteResult, result: ToolResult) -> None:
        """每个工具完成后立即更新状态，使后续步骤可以读取前置步骤结果。"""
        state.current_stage = route.stage
        if not result.success:
            state.last_error = result.error.code if result.error else "tool_error"
            return

        state.last_error = None
        if route.tool_name in {"plan_itinerary", "refine_itinerary"}:
            state.current_itinerary = str(result.data)
        elif route.tool_name == "estimate_budget":
            state.budget_plan = str(result.data)
        elif route.tool_name == "check_weather":
            state.weather_info = {"result": result.data, "metadata": result.metadata}
        elif route.tool_name == "convert_currency":
            state.exchange_info = {"result": result.data, "metadata": result.metadata}
