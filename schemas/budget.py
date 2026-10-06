from pydantic import BaseModel, Field


class BudgetItem(BaseModel):
    """定义 预算、记录 的结构化数据模型。"""
    category: str
    low: float | None = None
    medium: float | None = None
    high: float | None = None
    notes: str | None = None

# 定义 BudgetPlan 模型，用于保存预算计划信息，包括货币类型、预算项列表、总预算范围、假设条件和建议列表。
class BudgetPlan(BaseModel):
    """定义 预算、计划 的结构化数据模型。"""
    currency: str = "CNY"
    items: list[BudgetItem] = Field(default_factory=list)
    total_low: float | None = None
    total_medium: float | None = None
    total_high: float | None = None
    assumptions: list[str] = Field(default_factory=list)
    advice: list[str] = Field(default_factory=list)
