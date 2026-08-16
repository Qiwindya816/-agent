from pydantic import BaseModel

# 定义 ExchangeResult 模型，用于保存货币兑换结果，包括金额、源货币、目标货币、转换后的金额、汇率、日期、数据来源、是否不可用以及相关消息。
class ExchangeResult(BaseModel):
    amount: float
    from_currency: str
    to_currency: str
    converted_amount: float | None = None
    rate: float | None = None
    date: str | None = None
    source: str = "Frankfurter"
    unavailable: bool = False
    message: str | None = None
