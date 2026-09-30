"""Embedding service for RAG ingestion and retrieval."""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from config.settings import get_settings
from exceptions.llm import LLMServiceError


class EmbeddingService:
    """Generate embeddings using an OpenAI-compatible endpoint."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
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
        """Embed texts in batches and return vectors in input order."""
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
        """Embed a single retrieval query."""
        return self.embed_texts([text])[0]
