"""Tests for the DashScope-compatible Rerank client."""

import json

import httpx
import pytest

from exceptions.rerank import RerankServiceError
from services.rerank_service import RerankService


def test_rerank_service_sends_candidates_and_parses_indices() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.headers["Authorization"] == "Bearer test-key"
        assert payload["model"] == "qwen3-rerank"
        assert payload["input"] == {"query": "北京怎么玩", "documents": ["故宫", "量子计算"]}
        assert payload["parameters"]["top_n"] == 1
        return httpx.Response(
            200,
            json={"output": {"results": [{"index": 0, "relevance_score": 0.93}]}},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = RerankService(
        api_key="test-key",
        base_url="https://example.test/rerank",
        model="qwen3-rerank",
        client=client,
    )

    results = service.rerank("北京怎么玩", ["故宫", "量子计算"], top_n=1)

    assert [(item.index, item.relevance_score) for item in results] == [(0, pytest.approx(0.93))]


def test_rerank_service_rejects_invalid_result_index() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"output": {"results": [{"index": 9, "relevance_score": 0.8}]}},
            )
        )
    )
    service = RerankService(
        api_key="test-key",
        base_url="https://example.test/rerank",
        client=client,
    )

    with pytest.raises(RerankServiceError, match="index"):
        service.rerank("query", ["only document"])
