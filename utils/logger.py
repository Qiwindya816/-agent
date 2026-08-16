import logging

from config.settings import get_settings


def get_logger(name: str) -> logging.Logger:
    """获取写入运行日志文件的命名日志器，并避免重复添加处理器。"""
    settings = get_settings()
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(settings.log_dir / "runtime.log", encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
