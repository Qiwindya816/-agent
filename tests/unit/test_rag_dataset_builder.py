from evaluation.dataset_builder import (
    CorpusItem,
    build_gold_candidate,
    build_silver_payload,
    generate_annotations,
    select_balanced,
    validate_payload,
)


def item(number: int, *, city: str = "北京", theme: str = "food") -> CorpusItem:
    body = f"# 标题{number}\n\n这是用于测试的旅行信息，包含具体地点、交通方式、开放时间和注意事项。" * 3
    return CorpusItem(
        document_id=f"doc_{number}",
        chunk_id=f"chunk_{number}",
        city=city,
        theme=theme,
        title=f"标题{number}",
        chunk_text=body,
        source_name="小红书",
        source_url="https://www.xiaohongshu.com",
        authorization_status="research_only",
    )


def test_select_balanced_caps_each_city_theme_cell() -> None:
    items = [item(index) for index in range(5)] + [item(10 + index, theme="citywalk") for index in range(4)]
    selected = select_balanced(items, per_cell=2)
    assert len(selected) == 4
    assert len({value.document_id for value in selected}) == 4


def test_case_ids_do_not_collide_for_similar_theme_initials() -> None:
    items = [item(1, theme="food"), item(2, theme="family"), item(3, theme="night_tour"), item(4, theme="nearby_trip")]
    annotations, _ = generate_annotations(items)
    payload = build_silver_payload(items, annotations, user_id="demo", source_id=None)
    ids = [case["id"] for case in payload["cases"]]
    assert len(ids) == len(set(ids))


def test_generation_falls_back_and_payload_validates() -> None:
    items = [item(1), item(2)]
    annotations, warnings = generate_annotations(items, generator=lambda _: {"unexpected": []})
    assert warnings
    payload = build_silver_payload(items, annotations, user_id="demo", source_id=None)
    assert validate_payload(payload, {value.document_id: value for value in items}) == []


def test_gold_candidate_remains_pending_human_review() -> None:
    items = [item(1), item(2), item(3)]
    annotations, _ = generate_annotations(items)
    silver = build_silver_payload(items, annotations, user_id="demo", source_id=None)
    gold = build_gold_candidate(silver, per_cell=2)
    assert len(gold["cases"]) == 2
    assert gold["metadata"]["calibration_status"] == "pending_human_review"
    assert {case["review_status"] for case in gold["cases"]} == {"pending_human_review"}
