from typing import Any

from prompts.destination_prompt import build_destination_prompt
from schemas.tool import ToolResult
from services.llm_service import LLMService
from tools.base import BaseTool


class DestinationTool(BaseTool):
    """实现 destination 能力的统一工具接口。"""
    name = "recommend_destination"
    description = "根据用户偏好推荐旅行目的地。"

    def __init__(self, llm_service: LLMService | None = None) -> None:
        """初始化目的地推荐工具及其语言模型服务。"""
        self.llm_service = llm_service or LLMService()

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        """根据用户偏好生成目的地推荐结果。"""
        try:
            request = tool_input.get("contextual_input") or tool_input["user_input"]
            result = self.llm_service.generate_text(build_destination_prompt(request))
            return ToolResult.ok(self.name, result)
        except Exception as exc:
            return ToolResult.failure(self.name, "destination_tool_error", "目的地推荐失败。", details={"error": str(exc)})


def recommend_destination(user_profile: str) -> str:
    """以简化接口根据用户画像返回目的地推荐文本。"""
    result = DestinationTool().run({"user_input": user_profile})
    return str(result.data) if result.success else result.error.message
