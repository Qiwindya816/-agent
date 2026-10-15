from typing import Any

from pydantic import BaseModel, Field


class TravelRequest(BaseModel):
    """保存本次旅行的信息；这些字段不会写入用户的长期画像。"""

    departure_city: str | None = None  # 出发城市
    destination: str | None = None  # 目的地
    destination_level: str | None = None  # 目的地级别
    destination_country: str | None = None  # 国家
    destination_province: str | None = None  # 省份
    destination_city: str | None = None  # 城市
    start_date: str | None = None  # 开始日期
    end_date: str | None = None  # 结束日期
    travel_month: str | None = None  # 旅行月份
    travel_dates: str | None = None  # 旅行日期
    travel_days: int | None = None  # 天数
    travelers: int | None = None  # 同行人数
    budget: float | None = None  # 预算
    currency: str | None = None  # 币种
    interests: list[str] = Field(default_factory=list)  # 本次兴趣
    travel_style: str | None = None  # 本次风格
    special_requirements: list[str] = Field(default_factory=list)  # 特殊要求

    def apply_update(
        self,
        updates: "TravelRequest",
        *,
        clear_fields: list[str] | None = None,
        remove_items: dict[str, list[Any]] | None = None,
    ) -> "TravelRequest":
        """合并本轮旅行需求，并支持显式清空字段或删除列表项目。"""
        current = self.model_dump()
        # 合并非空更新
        for key, value in updates.model_dump().items():
            if value in (None, "", []):
                continue
            if isinstance(value, list):
                current[key] = list(dict.fromkeys([*(current.get(key) or []), *value]))
            else:
                current[key] = value
        # 删除列表里面指定的项
        for key, values in (remove_items or {}).items():
            if key in type(self).model_fields and isinstance(current.get(key), list):
                current[key] = [item for item in current[key] if item not in values]
        # 清理指定为空的字段
        for key in clear_fields or []:
            if key not in type(self).model_fields:
                continue
            annotation = type(self).model_fields[key].annotation
            current[key] = [] if "list" in str(annotation) else None
        return TravelRequest(**current)
