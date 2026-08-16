import re
from typing import Any

from schemas.tool import ToolResult
from services.exchange_service import ExchangeService
from tools.base import BaseTool


CURRENCY_ALIASES = {
    "人民币": "CNY",
    "元": "CNY",
    "块": "CNY",
    "rmb": "CNY",
    "cny": "CNY",
    "美元": "USD",
    "美金": "USD",
    "usd": "USD",
    "日元": "JPY",
    "jpy": "JPY",
    "韩元": "KRW",
    "krw": "KRW",
    "欧元": "EUR",
    "eur": "EUR",
    "英镑": "GBP",
    "gbp": "GBP",
}


class ExchangeTool(BaseTool):
    name = "convert_currency"
    description = "根据实时汇率换算货币。"

    def __init__(self, exchange_service: ExchangeService | None = None) -> None:
        """初始化换汇工具及其汇率服务。"""
        self.exchange_service = exchange_service or ExchangeService()

    def run(self, tool_input: dict[str, Any]) -> ToolResult:
        """解析换汇请求，查询实时汇率并格式化结果。"""
        parsed = _parse_exchange_request(tool_input["user_input"])
        if not parsed:
            return ToolResult.failure(self.name, "missing_exchange_args", "请提供金额、源币种和目标币种。")

        amount, source, target = parsed
        result = self.exchange_service.convert(amount, source, target)
        if result.unavailable:
            return ToolResult.failure(self.name, "exchange_unavailable", f"汇率服务暂时不可用：{result.message}", retryable=True)

        text = (
            "## 汇率换算\n\n"
            f"- 数据源：{result.source}\n"
            f"- 汇率日期：{result.date or 'latest'}\n"
            f"- 换算结果：**{result.amount:g} {result.from_currency} ≈ {result.converted_amount:.2f} {result.to_currency}**\n"
            f"- 参考汇率：1 {result.from_currency} ≈ {result.rate:.4f} {result.to_currency}"
        )
        return ToolResult.ok(self.name, text, metadata={"source": result.source, "date": result.date})

# 定义一个辅助函数，用于直接调用 ExchangeTool 并返回文本结果。
def convert_currency(travel_request: str) -> str:
    """以简化接口执行货币换算并直接返回文本。"""
    result = ExchangeTool().run({"user_input": travel_request})
    return str(result.data) if result.success else result.error.message

# 定义一个辅助函数，用于从文本中提取金额、源币种和目标币种，并返回一个元组或 None。
def _parse_exchange_request(text: str) -> tuple[float, str, str] | None:
    """从文本中按出现顺序提取金额、源币种和目标币种。"""
    amount_match = re.search(r"(\d+(?:\.\d+)?)", text) # 匹配数字金额，支持整数和小数
    if not amount_match:
        return None
    amount = float(amount_match.group(1))
    tokens = []
    lower_text = text.lower()
    for alias, code in CURRENCY_ALIASES.items():
        for match in re.finditer(re.escape(alias.lower()), lower_text):
            tokens.append((match.start(), code))
    ordered = []
    for _, code in sorted(tokens):
        if code not in ordered:
            ordered.append(code)
    if len(ordered) < 2:
        return None
    return amount, ordered[0], ordered[1]
