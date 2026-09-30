from typing import Any

from prompts.refine_prompt import build_refine_prompt
from schemas.itinerary import Itinerary
from schemas.tool import ToolResult
from services.llm_service import LLMService
from validators.itinerary_validator import ItineraryValidator
from tools.base import BaseTool


class ItineraryRefineTool(BaseTool):
    name = "refine_itinerary"
    description = "根据用户反馈修改已有行程。"

    def __init__(self, llm_service: LLMService | None = None) -> None:
        """初始化行程修改工具及其语言模型服务。"""
        self.llm_service = llm_service or LLMService()

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        """读取当前行程，并根据用户反馈生成修改后的版本。"""
        state = tool_input.get("state")
        current_itinerary = getattr(state, "structured_itinerary", None) or getattr(state, "current_itinerary", None)
        if not current_itinerary:
            return ToolResult.failure(
                self.name,
                "missing_current_itinerary",
                "当前还没有可修改的行程。请先创建一个行程。",
            )

        try:
            raw = self.llm_service.generate_json(
                build_refine_prompt(current_itinerary, tool_input["user_input"]),
                temperature=0,
            )
            itinerary = Itinerary.model_validate(raw)
            validation = ItineraryValidator().validate(itinerary)
            return ToolResult.ok(
                self.name,
                itinerary.model_dump(mode="json"),
                {
                    "schema": "Itinerary",
                    "schema_version": itinerary.schema_version,
                    "validation": validation.model_dump(mode="json"),
                },
            )
        except Exception as exc:
            return ToolResult.failure(self.name, "itinerary_refine_error", "行程修改失败。", details={"error": str(exc)})


def refine_itinerary(current_itinerary: str | None, user_feedback: str) -> dict[str, Any] | str:
    """以简化接口修改给定行程并返回结构化数据。"""
    class _State:
        pass

    state = _State()
    state.current_itinerary = current_itinerary
    result = ItineraryRefineTool().run({"state": state, "user_input": user_feedback})
    return result.data if result.success else result.error.message
