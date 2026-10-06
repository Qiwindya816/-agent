import json
import re

from schemas.route import RouteResult
from schemas.tool import ToolResult
from schemas.itinerary import Itinerary
from schemas.tool_outputs import NormalizedPoi, parse_poi_response
from services.itinerary_renderer import render_itinerary_markdown


class ResponseGenerator:
    """把结构化工具结果转换为用户可读文本。"""

    def generate(self, route: RouteResult, result: ToolResult, *, user_input: str = "") -> str:
        """将工具成功数据或错误信息转换为可展示的回复文本。"""
        if result.success:
            if result.metadata.get("schema") == "Itinerary" and isinstance(result.data, dict):
                return render_itinerary_markdown(Itinerary.model_validate(result.data))
            if route.tool_name == "search_poi":
                return self._render_poi_results(route, result, user_input)
            if isinstance(result.data, str):
                return result.data
            if isinstance(result.data, (dict, list)):
                return f"```json\n{json.dumps(result.data, ensure_ascii=False, indent=2)}\n```"
            return str(result.data)

        if result.error:
            return f"处理失败：{result.error.message}"

        return f"工具 {route.tool_name} 未返回有效结果。"

    def generate_many(
        self,
        results: list[tuple[RouteResult, ToolResult]],
        *,
        user_input: str = "",
    ) -> str:
        """把多个工具的结果合并成一条分节回复，保留每个任务的成功或失败信息。"""
        if len(results) == 1:
            return self.generate(*results[0], user_input=user_input)

        sections = []
        for route, result in results:
            # 多步骤回复中，汇总工具只负责后台落盘；不再重复展示前面的行程和预算。
            if route.tool_name == "finalize_plan" and result.success:
                continue
            title = {
                "recommend_destination": "目的地推荐",
                "plan_itinerary": "行程规划",
                "refine_itinerary": "行程调整",
                "estimate_budget": "预算估算",
                "check_weather": "天气查询",
                "convert_currency": "汇率换算",
                "finalize_plan": "方案汇总",
            }.get(route.tool_name, route.tool_name)
            sections.append(
                f"# {title}\n\n{self.generate(route, result, user_input=user_input)}"
            )
        return "\n\n---\n\n".join(sections)

    @staticmethod
    def _render_poi_results(route: RouteResult, result: ToolResult, user_input: str) -> str:
        """把地图供应商的原始 POI 数据整理为面向用户的地点推荐。"""
        pois = parse_poi_response(
            result.data,
            provider=str(result.metadata.get("provider") or "amap"),
        )
        if not pois:
            return "地图服务暂时没有找到符合条件的地点。可以换一个更具体的区域或景点类型再试。"

        filtered = _filter_pois(pois, user_input, route.arguments)
        if not filtered:
            return (
                "地图服务返回了一些地点，但没有找到足够符合你偏好且位置可靠的自然景点。"
                "建议把范围缩小到具体地铁站或街道后再查。"
            )

        lines = ["结合地图检索结果，比较符合你要求的有："]
        for index, poi in enumerate(filtered[:5], start=1):
            address = f"（{poi.address}）" if poi.address else ""
            lines.append(f"{index}. **{poi.name}**{address}")
        lines.append(
            "\n这些结果已排除明显的商场、产业园、停车场和餐饮等地点。"
            "地图文本检索本身不提供可靠的商业化程度与实时客流，出发前可再确认开放情况。"
        )
        return "\n".join(lines)


_NATURE_WORDS = ("自然", "公园", "湿地", "森林", "滨河", "河", "湖", "绿地", "郊野", "徒步")
_COMMERCIAL_WORDS = ("商场", "天街", "购物", "商业", "产业园", "工业园", "停车场", "酒店", "餐厅", "饭店", "中心")
_GENERIC_SEARCH_WORDS = (
    "附近", "周边", "自然景点", "自然", "景点", "公园", "湿地", "森林", "好去处", "游玩", "推荐",
)


def _filter_pois(
    pois: list[NormalizedPoi],
    user_input: str,
    arguments: dict,
) -> list[NormalizedPoi]:
    """按用户的自然/非商业偏好和地点关键词做保守的展示层过滤。"""
    wants_nature = any(word in user_input for word in _NATURE_WORDS)
    avoids_commercial = any(word in user_input for word in ("商业化", "不要商业", "不商业", "清静", "安静"))
    focus = _extract_location_focus(user_input, arguments)

    candidates = []
    for poi in pois:
        searchable = f"{poi.name} {poi.address or ''} {poi.category or ''}"
        typecode = poi.category or ""
        is_nature = typecode.startswith("11") or any(word in searchable for word in _NATURE_WORDS[1:])
        is_commercial = typecode.startswith(("02", "05", "06", "07", "10", "12", "15")) or any(
            word in searchable for word in _COMMERCIAL_WORDS
        )
        if wants_nature and not is_nature:
            continue
        if avoids_commercial and is_commercial:
            continue
        candidates.append(poi)

    if focus:
        local = [
            poi
            for poi in candidates
            if focus in f"{poi.name} {poi.address or ''} {poi.district or ''}"
        ]
        # 地图结果可能省略地址中的片区名；只有确有本地命中时才收紧范围。
        if local:
            candidates = local

    # 供应商偶尔返回重复记录，面向用户只保留同名地点一次。
    unique: list[NormalizedPoi] = []
    seen_names: set[str] = set()
    for poi in candidates:
        name = poi.name.strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        unique.append(poi)
    return unique


def _extract_location_focus(user_input: str, arguments: dict) -> str:
    """从“在 X 附近”或地图搜索词中提取用于过滤异地结果的片区名。"""
    match = re.search(r"(?:在|去)([\u4e00-\u9fffA-Za-z0-9·]{2,16}?)(?:附近|周边)", user_input)
    raw = match.group(1) if match else str(arguments.get("keywords") or "")
    for word in _GENERIC_SEARCH_WORDS:
        raw = raw.replace(word, " ")
    raw = re.sub(r"^(?:北京|北京市|上海|上海市|天津|天津市|重庆|重庆市)", "", raw.strip())
    tokens = [token for token in re.split(r"[\s,，、]+", raw) if 1 < len(token) <= 12]
    return tokens[0] if tokens else ""
