"""Evaluate current RAG recall against the minimal test set."""

import json
from pathlib import Path

from config.settings import get_settings
from db.engine import DatabaseEngine
from services.embedding_service import EmbeddingService
from services.rag_retrieval import RagRetrievalService


def main() -> int:
    engine = DatabaseEngine(get_settings().database_url)
    retrieval = RagRetrievalService(engine, EmbeddingService())
    cases = json.loads(Path("tests/rag_eval_cases.json").read_text(encoding="utf-8"))
    failures = []
    for index, case in enumerate(cases, start=1):
        results = retrieval.search("eval_user", case["query"], **case.get("filters", {}))
        matched = any(
            all(token in item.chunk_text for token in case["expected_chunk_text_contains"])
            for item in results
        )
        print(f"case={index} query={case['query']} hit={int(matched)} result_count={len(results)}")
        if not matched:
            failures.append(index)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
