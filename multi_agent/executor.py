from schemas.agent_state import AgentState
from collections.abc import Callable
from typing import Any

from schemas.route import RoutePlan, RouteResult
from schemas.tool import ToolResult
from services.context_builder import ContextBuilder
from services.itinerary_enricher import ItineraryEnricher
from services.itinerary_map_service import ItineraryMapService
from services.memory_conflict_resolver import MemoryConflictResolver
from services.memory_retrieval import MemoryRetrievalService
from repositories.trip_feedback_repository import TripFeedbackRepository
from repositories.trip_repository import ItineraryVersionService
from services.personalization_ranking import PersonalizationRankingService, render_ranking_explanation
from services.rag_retrieval import RagRetrievalService
from tools.registry import ToolRegistry, build_default_registry


class ToolExecutor:
    """从工具注册表中查找并执行工具，统一处理工具结果。"""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        context_builder: ContextBuilder | None = None,
        enricher: ItineraryEnricher | None = None,
        rag_retrieval: RagRetrievalService | None = None,
        memory_retrieval: MemoryRetrievalService | None = None,
        memory_resolver: MemoryConflictResolver | None = None,
        ranking_service: PersonalizationRankingService | None = None,
    ) -> None:
        """初始化执行器；未传入注册表时创建默认工具注册表。"""
        self.registry = registry or build_default_registry()
        self.context_builder = context_builder or ContextBuilder()
        self.enricher = enricher or ItineraryEnricher()
        self.map_service = ItineraryMapService()
        self.rag_retrieval = rag_retrieval or RagRetrievalService()
        from services.embedding_service import EmbeddingService
        self.memory_retrieval = memory_retrieval or MemoryRetrievalService(embedding_service=EmbeddingService())
        self.memory_resolver = memory_resolver or MemoryConflictResolver()
        self.ranking_service = ranking_service or PersonalizationRankingService()

    def execute(self, route: RouteResult, user_input: str, state: AgentState) -> ToolResult:
        """根据路由结果查找并执行工具，统一返回 ToolResult。"""
        tool = self.registry.get(route.tool_name) # tool是一个BaseTool实例
        if not tool:
            return ToolResult.failure(
                tool_name=route.tool_name,
                code="tool_not_found",
                message=f"未找到工具：{route.tool_name}",
            )

        memory_results = self.memory_resolver.resolve(
            self.memory_retrieval.retrieve(state.user_id, user_input)
        ) if self._personalization_enabled(state.user_id) else []
        rag_results = self.rag_retrieval.search(
            state.user_id,
            user_input,
            city=state.travel_request.destination,
            theme=state.travel_request.travel_style,
            travel_days=state.travel_request.travel_days,
        ) if route.tool_name in {"plan_itinerary", "refine_itinerary", "recommend_destination", "estimate_budget"} else []
        tool_input = {
            "user_input": user_input,
            "contextual_input": self.context_builder.build(
                state,
                user_input,
                memory_results=memory_results,
                rag_results=rag_results,
            ),
            "state": state,
            "route": route,
            "mcp_arguments": route.arguments,
        }
        result = tool.run(tool_input)
        if memory_results:
            state.active_memories = [
                {
                    "memory_type": decision.memory.memory_type,
                    "category": decision.memory.category,
                    "statement": decision.memory.statement,
                    "structured_value": decision.memory.structured_value,
                    "scope": decision.memory.scope,
                    "confidence": decision.memory.confidence,
                    "evidence_count": decision.memory.evidence_count,
                    "reason": decision.reason,
                }
                for decision in memory_results[:5]
            ]
        ranking_explanation = ""
        parsed_itinerary = None
        if (
            result.success
            and route.tool_name in {"plan_itinerary", "refine_itinerary", "edit_itinerary_activity"}
            and isinstance(result.data, dict)
        ):
            from schemas.itinerary import Itinerary
            parsed_itinerary = Itinerary.model_validate(result.data)
            geocode_tool = self.registry.get("geocode")
            if geocode_tool is not None:
                parsed_itinerary, map_result, resolved = self.map_service.enrich(
                    parsed_itinerary,
                    geocode_tool,
                    state,
                )
                result.data = parsed_itinerary.model_dump(mode="json", exclude_none=True)
                result.metadata["map_enrichment"] = {
                    "success": map_result.success,
                    "resolved_activities": resolved,
                    "error": map_result.error.model_dump(mode="json") if map_result.error else None,
                }
        candidate_itinerary = parsed_itinerary or state.structured_itinerary
        if (
            result.success
            and route.tool_name in {"plan_itinerary", "refine_itinerary", "edit_itinerary_activity"}
            and candidate_itinerary
        ):
            activities = [
                activity
                for day in candidate_itinerary.days
                for activity in day.activities
            ]
            ranked = self.ranking_service.rank(
                activities,
                memories=[decision.memory for decision in memory_results],
                budget=state.travel_request.budget,
            )
            ranking_explanation = render_ranking_explanation(ranked)
            result.metadata["ranking"] = [item.model_dump(mode="json") for item in ranked]
            result.metadata["ranking_explanation"] = ranking_explanation
            try:
                from db.engine import get_database_engine

                database = get_database_engine()
                change_reason = str(result.metadata.get("change_reason") or user_input)
                version = ItineraryVersionService(database).save_version(
                    state.user_id,
                    state.session_id,
                    state.trip_id,
                    candidate_itinerary,
                    change_reason=change_reason,
                    source_agent=route.tool_name,
                )
                result.metadata["version_id"] = version.version_id
                result.metadata["version_number"] = version.version_number
                with database.session() as session:
                    TripFeedbackRepository(session).create(
                        state.user_id,
                        state.trip_id,
                        version_id=version.version_id,
                        feedback_type="modify" if route.tool_name != "plan_itinerary" else "accept",
                        reason=change_reason,
                    )
            except Exception:
                # 行程版本持久化失败不能阻断面向用户的生成主链路。
                pass

        if result.success and state.structured_itinerary:
            if route.tool_name == "search_poi":
                state.structured_itinerary = self.enricher.enrich_from_poi(
                    state.structured_itinerary,
                    result,
                    detail_tool=self.registry.get("search_poi_detail"),
                )
            elif route.tool_name == "plan_route":
                state.structured_itinerary = self.enricher.enrich_from_route(
                    state.structured_itinerary,
                    result,
                    route=route,
                )
            elif route.tool_name == "check_weather":
                state.structured_itinerary = self.enricher.add_weather_warning(
                    state.structured_itinerary,
                    result,
                )
            elif route.tool_name in {"query_train_tickets", "query_train_price", "query_train_transfer"}:
                state.structured_itinerary = self.enricher.add_transport_options(
                    state.structured_itinerary,
                    result,
                    train_date=route.arguments.get("train_date"),
                )
        return result

    @staticmethod
    def _build_contextual_input(user_input: str, state: AgentState) -> str:
        """把长期偏好、当前旅行和已有行程注入生成型工具，支持跨轮次需求。"""
        parts = [
            f"长期用户偏好：{state.user_profile.model_dump_json(exclude_none=True)}",
            f"当前旅行需求：{state.travel_request.model_dump_json(exclude_none=True)}",
        ]
        if state.structured_itinerary:
            parts.append(f"当前结构化行程：\n{state.structured_itinerary.model_dump_json(exclude_none=True)}")
        elif state.current_itinerary:
            parts.append(f"当前已有行程：\n{state.current_itinerary}")
        parts.append(f"用户本轮输入：{user_input}")
        return "\n\n".join(parts)

    @staticmethod
    def _personalization_enabled(user_id: str) -> bool:
        """处理 `_personalization_enabled` 对应的数据和流程，返回该步骤的处理结果。"""
        from config.settings import get_settings
        from db.engine import get_database_engine
        from db.models import User

        try:
            with get_database_engine().session() as session:
                user = session.get(User, user_id)
                return bool(user is None or user.personalization_enabled)
        except Exception:
            return False

    def execute_plan(
        self,
        plan: RoutePlan,
        user_input: str,
        state: AgentState,
        *,
        after_each: Callable[[RouteResult, ToolResult], None] | None = None,
    ) -> list[tuple[RouteResult, ToolResult]]:
        """按计划顺序执行多个工具，并在每步结束后允许工作流立即更新状态。"""
        completed: list[tuple[RouteResult, ToolResult]] = []
        successful_tools: set[str] = set()
        geocode_results: list[dict[str, str]] | None = None
        for step in plan.steps:
            if step.tool_name == "plan_route" and geocode_results:
                _fill_route_arguments(step, geocode_results)
            unmet_dependencies = [name for name in step.depends_on if name not in successful_tools]
            if unmet_dependencies:
                result = ToolResult.failure(
                    step.tool_name,
                    "dependency_failed",
                    f"前置任务未成功：{', '.join(unmet_dependencies)}",
                )
            else:
                result = self.execute(step, user_input, state)

            completed.append((step, result))
            if result.success:
                successful_tools.add(step.tool_name)
                if step.tool_name == "geocode":
                    geocode_results = _extract_geocode_locations(result.data)
            if after_each:
                after_each(step, result)
            if not result.success and not plan.continue_on_error:
                break
        return completed



def _extract_geocode_locations(data: Any) -> list[dict[str, str]]:
    """从聚合 geocode 结果中提取地址、坐标和城市。"""
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        return []
    locations = []
    for item in data["results"]:
        if not isinstance(item, dict) or not item.get("location"):
            continue
        locations.append(
            {
                "address": str(item.get("address") or ""),
                "location": str(item["location"]),
                "city": str(item.get("city") or ""),
            }
        )
    return locations


def _fill_route_arguments(step: RouteResult, locations: list[dict[str, str]]) -> None:
    """把 geocode 返回的坐标回填到依赖它的路线步骤。"""
    if _is_coordinate(step.arguments.get("origin")) and _is_coordinate(step.arguments.get("destination")):
        return
    if not locations:
        return

    by_address = {item["address"]: item for item in locations if item["address"]}

    def resolve(name: Any, index: int) -> str:
        """递归解析参数中的状态引用和前序工具结果。"""
        text = str(name or "").strip()
        if _is_coordinate(text):
            return text
        if text and text in by_address:
            return by_address[text]["location"]
        if not text and index < len(locations):
            return locations[index]["location"]
        return text

    step.arguments["origin"] = resolve(step.arguments.get("origin"), 0)
    step.arguments["destination"] = resolve(step.arguments.get("destination"), 1)
    city = locations[0].get("city") or "北京"
    cityd = locations[-1].get("city") or city
    step.arguments.setdefault("city", city)
    step.arguments.setdefault("cityd", cityd)


def _is_coordinate(value: Any) -> bool:
    """判断高德路线参数是否已经是“经度,纬度”。"""
    if not isinstance(value, str):
        return False
    parts = value.split(",")
    if len(parts) != 2:
        return False
    try:
        longitude, latitude = float(parts[0]), float(parts[1])
    except ValueError:
        return False
    return -180 <= longitude <= 180 and -90 <= latitude <= 90
