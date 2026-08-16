from collections.abc import Callable
from time import sleep
from typing import TypeVar


T = TypeVar("T")


def retry(callable_: Callable[[], T], *, attempts: int = 2, delay_seconds: float = 0.2) -> T:
    """按指定次数重试可调用对象，全部失败后重新抛出最后一次异常。"""
    last_error: Exception | None = None
    for index in range(attempts):
        try:
            return callable_()
        except Exception as exc:
            last_error = exc
            if index < attempts - 1:
                sleep(delay_seconds)
    raise last_error  # type: ignore[misc]
