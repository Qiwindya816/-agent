from pydantic import BaseModel, Field

from schemas.budget import BudgetPlan


class BudgetValidationResult(BaseModel):
    """承载 预算、校验 的结构化结果。"""
    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class BudgetValidator:
    """集中校验 预算 的业务约束。"""
    def validate(self, budget: BudgetPlan, budget_limit: float | None = None) -> BudgetValidationResult:
        """检查预算金额是否为负，并提示中等方案是否超出预算上限。"""
        errors = []
        warnings = []

        for item in budget.items:
            for field in ["low", "medium", "high"]:
                value = getattr(item, field) # 获取预算项的低、中、高费用
                if value is not None and value < 0:
                    errors.append(f"{item.category} 的 {field} 费用不能为负数。")

        if budget_limit and budget.total_medium and budget.total_medium > budget_limit:
            warnings.append("中等预算方案超过用户预算。")

        return BudgetValidationResult(is_valid=not errors, errors=errors, warnings=warnings)
