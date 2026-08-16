from exceptions.base import TravelMindError


class LLMServiceError(TravelMindError):
    """LLM 服务调用失败。"""


class InvalidLLMOutputError(LLMServiceError):
    """LLM 输出无法按预期解析。"""
