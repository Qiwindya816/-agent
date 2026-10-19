"""封装文本相关性重排服务。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from config.settings import get_settings
from exceptions.rerank import RerankServiceError


@dataclass(frozen=True)
class RerankResult:
    """一条候选文档的精排结果。"""

    index: int
    relevance_score: float


class Reranker(Protocol):
    """检索层依赖的最小精排接口，便于替换供应商和注入测试实现。"""

    def rerank(self, query: str, documents: list[str], *, top_n: int | None = None) -> list[RerankResult]: ...


class RerankService:
    """调用 DashScope 文本排序 HTTP API，并返回原候选索引和相关性分数。"""

    DEFAULT_INSTRUCTION = "Given a web search query, retrieve relevant passages that answer the query."

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key or settings.dashscope_api_key
        self.base_url = base_url or settings.rag_rerank_base_url
        self.model = model or settings.rag_rerank_model
        self.timeout = timeout or settings.rag_rerank_timeout_seconds
        self._client = client

    def rerank(self, query: str, documents: list[str], *, top_n: int | None = None) -> list[RerankResult]:
        """按照查询相关性重排候选文本。"""
        if not documents:
            return []
        if not query.strip():
            raise RerankServiceError("Rerank query cannot be empty.")
        if not self.api_key:
            raise RerankServiceError("缺少 DASHSCOPE_API_KEY，无法调用 Rerank 服务。")
        if not self.base_url:
            raise RerankServiceError("缺少 RAG_RERANK_BASE_URL，无法调用 Rerank 服务。")

        result_count = min(top_n or len(documents), len(documents))
        payload = {
            "model": self.model,
            "input": {"query": query, "documents": documents},
            "parameters": {
                "top_n": result_count,
                "return_documents": False,
                "instruct": self.DEFAULT_INSTRUCTION,
            },
        }
        try:
            response = self._post(payload)
            response.raise_for_status()
            body = response.json()
            return self._parse_results(body, document_count=len(documents))
        except RerankServiceError:
            raise
        except (httpx.HTTPError, TypeError, ValueError, KeyError) as exc:
            raise RerankServiceError(f"Rerank request failed: {exc}") from exc

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self._client is not None:
            return self._client.post(self.base_url, headers=headers, json=payload, timeout=self.timeout)
        return httpx.post(self.base_url, headers=headers, json=payload, timeout=self.timeout)

    @staticmethod
    def _parse_results(body: dict[str, Any], *, document_count: int) -> list[RerankResult]:
        raw_results = body.get("output", {}).get("results")
        if not isinstance(raw_results, list):
            message = body.get("message") or "response does not contain output.results"
            raise RerankServiceError(f"Invalid Rerank response: {message}")

        parsed: list[RerankResult] = []
        seen: set[int] = set()
        for item in raw_results:
            if not isinstance(item, dict):
                raise RerankServiceError("Invalid Rerank result item.")
            index = item.get("index")
            score = item.get("relevance_score")
            if not isinstance(index, int) or not 0 <= index < document_count:
                raise RerankServiceError(f"Invalid Rerank result index: {index!r}")
            if index in seen:
                raise RerankServiceError(f"Duplicate Rerank result index: {index}")
            if not isinstance(score, (int, float)):
                raise RerankServiceError(f"Invalid Rerank relevance score: {score!r}")
            seen.add(index)
            parsed.append(RerankResult(index=index, relevance_score=float(score)))
        return parsed
