from schemas.route import RouteResult
from schemas.tool import ToolResult


class ResponseGenerator:
    """把结构化工具结果转换为用户可读文本。"""

    def generate(self, route: RouteResult, result: ToolResult) -> str:
        """将工具成功数据或错误信息转换为可展示的回复文本。"""
        if result.success:
            if isinstance(result.data, str):
                return result.data
            return str(result.data)

        if result.error:
            return f"处理失败：{result.error.message}"

        return f"工具 {route.tool_name} 未返回有效结果。"

    def generate_many(self, results: list[tuple[RouteResult, ToolResult]]) -> str:
        """把多个工具的结果合并成一条分节回复，保留每个任务的成功或失败信息。"""
        if len(results) == 1:
            return self.generate(*results[0])

        sections = []
        for route, result in results:
            title = {
                "recommend_destination": "目的地推荐",
                "plan_itinerary": "行程规划",
                "refine_itinerary": "行程调整",
                "estimate_budget": "预算估算",
                "check_weather": "天气查询",
                "convert_currency": "汇率换算",
                "finalize_plan": "方案汇总",
            }.get(route.tool_name, route.tool_name)
            sections.append(f"# {title}\n\n{self.generate(route, result)}")
        return "\n\n---\n\n".join(sections)
