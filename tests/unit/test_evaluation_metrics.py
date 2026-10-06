from evaluation.itinerary import evaluate_itineraries
from evaluation.metrics import ndcg_at_k, precision_at_k, recall_at_k
from evaluation.rag import evaluate_rag_cases


def test_ir_metrics_are_deterministic() -> None:
    assert precision_at_k([2, 0, 1], 3) == 2 / 3
    assert recall_at_k(2, 4) == 0.5
    assert ndcg_at_k([2, 1, 0], [2, 1], 3) == 1.0


class FakeRetrieval:
    def search(self, user_id, query, **kwargs):
        return [
            {
                "rank": 1,
                "chunk_id": "c1",
                "document_id": "d1",
                "chunk_text": "北京公园适合散步",
                "source_name": "测试来源",
                "source_url": "https://example.com/1",
                "source_authorization_status": "authorized",
                "fetched_at": "2026-10-05",
            },
            {
                "rank": 2,
                "chunk_id": "c2",
                "document_id": "d2",
                "chunk_text": "无关内容",
                "source_name": "测试来源",
                "source_url": "https://example.com/2",
                "source_authorization_status": "authorized",
                "fetched_at": "2026-10-05",
            },
        ]


def test_rag_evaluation_scores_relevance_and_traceability() -> None:
    report = evaluate_rag_cases(
        FakeRetrieval(),
        [{"id": "r1", "query": "公园", "relevant": [{"contains_any": ["公园"], "relevance": 2}]}],
        default_user_id="user_a",
        k=2,
    )

    assert report["macro_metrics"]["recall@2"] == 1.0
    assert report["macro_metrics"]["precision@2"] == 0.5
    assert report["macro_metrics"]["source_traceability"] == 1.0
    assert report["cases"][0]["results"][0]["chunk_id"] == "c1"


def test_itinerary_evaluation_detects_conflict_and_budget_overrun() -> None:
    report = evaluate_itineraries([
        {
            "id": "bad",
            "budget_limit": 100,
            "itinerary": {
                "travel_days": 1,
                "total_estimated_cost": 150,
                "days": [{
                    "day": 1,
                    "activities": [
                        {"activity_id": "a", "name": "A", "start_time": "09:00", "end_time": "11:00"},
                        {"activity_id": "b", "name": "B", "start_time": "10:00", "end_time": "12:00"}
                    ]
                }]
            }
        }
    ])

    assert report["metrics"]["time_conflict_rate"] == 1.0
    assert report["metrics"]["budget_overrun_rate"] == 1.0
    assert report["metrics"]["route_infeasible_rate"] == 1.0
