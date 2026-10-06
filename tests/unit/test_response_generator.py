from multi_agent.summarizer import ResponseGenerator
from schemas.route import RouteResult
from schemas.tool import ToolResult


def test_multi_step_response_hides_finalize_confirmation() -> None:
    results = [
        (RouteResult(intent="plan", tool_name="plan_itinerary", confidence=1), ToolResult.ok("plan_itinerary", "行程正文")),
        (RouteResult(intent="final", tool_name="finalize_plan", confidence=1), ToolResult.ok("finalize_plan", "后台已保存")),
    ]

    response = ResponseGenerator().generate_many(results)

    assert "行程正文" in response
    assert "后台已保存" not in response
    assert "方案汇总" not in response


def test_poi_response_is_filtered_and_rendered_for_users() -> None:
    route = RouteResult(
        intent="poi",
        tool_name="search_poi",
        confidence=1,
        arguments={"keywords": "亦庄"},
    )
    result = ToolResult.ok(
        "search_poi",
        {
            "pois": [
                {"id": "park-1", "name": "亦庄公园", "address": "亦庄桥西150米", "typecode": "110101"},
                {"id": "mall-1", "name": "龙湖北京亦庄天街", "address": "博兴八路", "typecode": "060101"},
                {"id": "factory-1", "name": "北京亦庄产业园", "address": "科谷四街", "typecode": "120100"},
                {"id": "far-1", "name": "奥林匹克公园湿地", "address": "朝阳区科荟路", "typecode": "110200"},
                {"id": "park-2", "name": "亦庄新城滨河森林公园", "address": "北京经济技术开发区", "typecode": "110101"},
            ]
        },
        {"provider": "amap"},
    )

    response = ResponseGenerator().generate_many(
        [(route, result)],
        user_input="我想在北京亦庄附近游玩，偏爱自然景点，不要商业化严重的",
    )

    assert "亦庄公园" in response
    assert "亦庄新城滨河森林公园" in response
    assert "天街" not in response
    assert "北京亦庄产业园" not in response
    assert "奥林匹克公园" not in response
    assert "park-1" not in response
    assert "typecode" not in response
    assert "```json" not in response
