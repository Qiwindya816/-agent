import requests

from config.settings import get_settings
from schemas.exchange import ExchangeResult


FRANKFURTER_URL = "https://api.frankfurter.app/latest"


class ExchangeService:
    """提供 exchange 相关的领域服务。"""
    def __init__(self) -> None:
        """加载汇率接口请求所需的项目配置。"""
        self.settings = get_settings()

    def convert(self, amount: float, from_currency: str, to_currency: str) -> ExchangeResult:
        """调用 Frankfurter 换算货币，并以统一模型返回结果或错误。"""
        from_currency = from_currency.upper() # 设置源货币为大写
        to_currency = to_currency.upper() # 设置目标货币为大写
        if from_currency == to_currency:
            return ExchangeResult(
                amount=amount,
                from_currency=from_currency,
                to_currency=to_currency,
                converted_amount=amount,
                rate=1,
            )

        try:
            response = requests.get(
                FRANKFURTER_URL,
                params={"amount": amount, "from": from_currency, "to": to_currency},
                timeout=self.settings.api_timeout,
            )
            response.raise_for_status() # 如果响应状态码不是 200，会抛出 HTTPError 异常
            data = response.json()
            converted = (data.get("rates") or {}).get(to_currency)
            if converted is None:
                raise ValueError(f"接口没有返回 {from_currency} 到 {to_currency} 的汇率。")
            return ExchangeResult(
                amount=amount,
                from_currency=from_currency,
                to_currency=to_currency,
                converted_amount=converted,
                rate=converted / amount if amount else None,
                date=data.get("date"),
            )
        except Exception as exc:
            return ExchangeResult(
                amount=amount,
                from_currency=from_currency,
                to_currency=to_currency,
                unavailable=True,
                message=str(exc),
            )
