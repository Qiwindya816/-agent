from pydantic import BaseModel, Field

from schemas.agent_state import AgentState


class StateValidationResult(BaseModel):
    is_valid: bool
    errors: list[str] = Field(default_factory=list)


class StateValidator:
    def validate_refine_ready(self, state: AgentState) -> StateValidationResult:
        """检查当前状态是否已有可供修改的行程。"""
        if not state.current_itinerary:
            return StateValidationResult(is_valid=False, errors=["当前没有可修改的行程。"])
        return StateValidationResult(is_valid=True)
