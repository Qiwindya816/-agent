from pydantic import BaseModel, Field

from schemas.travel_request import TravelRequest


class RequestValidationResult(BaseModel):
    """承载 请求、校验 的结构化结果。"""
    is_complete: bool
    missing_fields: list[str] = Field(default_factory=list)
    invalid_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RequestValidator:
    """集中校验 请求 的业务约束。"""
    def validate_for_itinerary(self, request: TravelRequest) -> RequestValidationResult:
        """检查生成行程所需字段是否完整且取值有效。"""
        missing = []
        invalid = []

        if not request.destination:
            missing.append("destination")
        if not request.travel_days and not (request.start_date and request.end_date):
            missing.append("travel_days 或 start_date/end_date")
        if request.budget is not None and request.budget <= 0:
            invalid.append("budget")
        if request.travelers <= 0:
            invalid.append("travelers")

        return RequestValidationResult(
            is_complete=not missing and not invalid,
            missing_fields=missing,
            invalid_fields=invalid,
        )
