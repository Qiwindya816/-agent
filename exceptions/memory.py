from exceptions.base import TravelMindError


class MemoryReadError(TravelMindError):
    """记忆读取失败。"""


class MemoryWriteError(TravelMindError):
    """记忆写入失败。"""
