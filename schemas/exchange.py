from pydantic import BaseModel

# 定义 ExchangeResult 模型，用于保存货币兑换结果，包括金额、源货币、目标货币、转换后的金额、汇率、日期、数据来源、是否不可用以及相关消息。
class ExchangeResult(BaseModel):
    """承载 exchange 的结构化结果。"""
    amount: float  # 原始金额
    from_currency: str  # 源币种
    to_currency: str  # 目标币种
    converted_amount: float | None = None  # 换算后金额
    rate: float | None = None  # 参考汇率
    date: str | None = None  # 汇率日期
    source: str = "Frankfurter"  # 数据源
    unavailable: bool = False  # 服务是否不可用
    message: str | None = None  # 错误信息
