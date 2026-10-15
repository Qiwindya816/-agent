from pydantic import BaseModel, Field


class BudgetItem(BaseModel):
    """定义 预算、记录 的结构化数据模型。"""
    category: str  # 预算类别
    low: float | None = None  # 低档预算
    medium: float | None = None  # 中档预算
    high: float | None = None  # 高档预算
    notes: str | None = None  # 说明

# 定义 BudgetPlan 模型，用于保存预算计划信息，包括货币类型、预算项列表、总预算范围、假设条件和建议列表。
class BudgetPlan(BaseModel):
    """定义 预算、计划 的结构化数据模型。"""
    currency: str = "CNY"  # 币种
    items: list[BudgetItem] = Field(default_factory=list)  # 预算项列表
    total_low: float | None = None  # 低档合计
    total_medium: float | None = None  # 中档合计
    total_high: float | None = None  # 高档合计
    assumptions: list[str] = Field(default_factory=list)  # 预算假设
    advice: list[str] = Field(default_factory=list)  # 预算建议
