"""提供 核心领域服务和外部服务适配；本文件负责 `embedding_service` 相关实现。"""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from config.settings import get_settings
from exceptions.llm import LLMServiceError


class EmbeddingService:
    """提供 `EmbeddingService` 对应领域能力的统一服务。"""

    def __init__(self) -> None:
        """初始化 EmbeddingService 及其运行依赖。"""
        self.settings = get_settings()
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        """延迟创建并复用 OpenAI 兼容的向量模型客户端。"""
        if not self.settings.dashscope_api_key:
            raise LLMServiceError("缺少 DASHSCOPE_API_KEY，请在本地 .env 文件中配置。")
        if self._client is None:
            self._client = OpenAI(
                api_key=self.settings.dashscope_api_key,
                base_url=self.settings.embedding_base_url,
                timeout=self.settings.api_timeout,
                max_retries=self.settings.max_retries,
            )
        return self._client

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """生成向量 `embed_texts` 对应的数据和流程，返回该步骤的处理结果。"""
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.settings.embedding_batch_size):
            batch = texts[start : start + self.settings.embedding_batch_size]
            response = self.client.embeddings.create(
                model=self.settings.embedding_model,
                input=batch,
                dimensions=self.settings.embedding_dimensions,
            )
            vectors.extend([item.embedding for item in response.data])
        return vectors

    def embed_query(self, text: str) -> list[float]:
        """生成向量 `embed_query` 对应的数据和流程，返回该步骤的处理结果。"""
        return self.embed_texts([text])[0]
