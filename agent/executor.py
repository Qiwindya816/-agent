from schemas.agent_state import AgentState
from collections.abc import Callable

from schemas.route import RoutePlan, RouteResult
from schemas.tool import ToolResult
from tools.registry import ToolRegistry, build_default_registry


class ToolExecutor:
    """从工具注册表中查找并执行工具，统一处理工具结果。"""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        """初始化执行器；未传入注册表时创建默认工具注册表。"""
        self.registry = registry or build_default_registry()

    def execute(self, route: RouteResult, user_input: str, state: AgentState) -> ToolResult:
        """根据路由结果查找并执行工具，统一返回 ToolResult。"""
        tool = self.registry.get(route.tool_name) # tool是一个BaseTool实例
        if not tool:
            return ToolResult.failure(
                tool_name=route.tool_name,
                code="tool_not_found",
                message=f"未找到工具：{route.tool_name}",
            )

        tool_input = {
            "user_input": user_input,
            "contextual_input": self._build_contextual_input(user_input, state),
            "state": state,
            "route": route,
        }
        return tool.run(tool_input)

    @staticmethod
    def _build_contextual_input(user_input: str, state: AgentState) -> str:
        """把长期偏好、当前旅行和已有行程注入生成型工具，支持跨轮次需求。"""
        parts = [
            f"长期用户偏好：{state.user_profile.model_dump_json(exclude_none=True)}",
            f"当前旅行需求：{state.travel_request.model_dump_json(exclude_none=True)}",
        ]
        if state.current_itinerary:
            parts.append(f"当前已有行程：\n{state.current_itinerary}")
        parts.append(f"用户本轮输入：{user_input}")
        return "\n\n".join(parts)

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
        for step in plan.steps:
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
            if after_each:
                after_each(step, result)
            if not result.success and not plan.continue_on_error:
                break
        return completed
