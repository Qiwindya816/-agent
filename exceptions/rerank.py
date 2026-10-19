from exceptions.base import TravelMindError


class RerankServiceError(TravelMindError):
    """Rerank 服务配置错误、请求失败或响应格式异常。"""
