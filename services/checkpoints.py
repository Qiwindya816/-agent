"""提供 核心领域服务和外部服务适配；本文件负责 `checkpoints` 相关实现。"""

from __future__ import annotations

from typing import Any

import psycopg

from config.settings import get_settings


def build_checkpointer(*, setup: bool = True) -> Any:
    """根据配置创建 LangGraph checkpoint 保存器。"""
    settings = get_settings()
    backend = settings.checkpoint_backend.lower()

    if backend == "postgresql" and settings.database_url.startswith("postgresql"):
        PostgresSaver = globals().get("PostgresSaver")
        if PostgresSaver is None:
            from langgraph.checkpoint.postgres import PostgresSaver

        connection_string = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
        connection = psycopg.connect(connection_string, autocommit=True, prepare_threshold=0)
        saver = PostgresSaver(connection)
        if setup:
            saver.setup()
        return saver

    from langgraph.checkpoint.memory import InMemorySaver

    return InMemorySaver()
