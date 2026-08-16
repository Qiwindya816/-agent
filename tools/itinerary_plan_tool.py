from typing import Any

from prompts.itinerary_prompt import build_itinerary_prompt
from schemas.tool import ToolResult
from services.llm_service import LLMService
from tools.base import BaseTool


class ItineraryPlanTool(BaseTool):
    name = "plan_itinerary"
    description = "根据用户需求规划新的旅行行程。"

    def __init__(self, llm_service: LLMService | None = None) -> None:
        """初始化行程规划工具及其语言模型服务。"""
        self.llm_service = llm_service or LLMService()

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        """根据用户需求调用语言模型生成新行程。"""
        try:
            request = tool_input.get("contextual_input") or tool_input["user_input"]
            result = self.llm_service.generate_text(build_itinerary_prompt(request))
            return ToolResult.ok(self.name, result)
        except Exception as exc:
            return ToolResult.failure(self.name, "itinerary_plan_error", "行程规划失败。", details={"error": str(exc)})


def plan_itinerary(travel_request: str) -> str:
    """以简化接口规划旅行行程并直接返回文本。"""
    result = ItineraryPlanTool().run({"user_input": travel_request})
    return str(result.data) if result.success else result.error.message
