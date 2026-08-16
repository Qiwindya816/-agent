from typing import Any

from prompts.budget_prompt import build_budget_prompt
from schemas.tool import ToolResult
from services.llm_service import LLMService
from tools.base import BaseTool


class BudgetTool(BaseTool):
    name = "estimate_budget"
    description = "估算旅行预算。"

    def __init__(self, llm_service: LLMService | None = None) -> None:
        """初始化预算工具及其语言模型服务。"""
        self.llm_service = llm_service or LLMService()

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        """根据用户旅行需求生成预算估算结果。"""
        try:
            request = tool_input.get("contextual_input") or tool_input["user_input"]
            result = self.llm_service.generate_text(build_budget_prompt(request))
            return ToolResult.ok(self.name, result)
        except Exception as exc:
            return ToolResult.failure(self.name, "budget_tool_error", "预算估算失败。", details={"error": str(exc)})


def estimate_budget(travel_request: str) -> str:
    """以简化接口估算预算，并直接返回文本结果。"""
    result = BudgetTool().run({"user_input": travel_request})
    return str(result.data) if result.success else result.error.message
