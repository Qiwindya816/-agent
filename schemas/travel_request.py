from typing import Any

from pydantic import BaseModel, Field


class TravelRequest(BaseModel):
    """保存本次旅行的信息；这些字段不会写入用户的长期画像。"""

    departure_city: str | None = None
    destination: str | None = None
    destination_level: str | None = None
    destination_country: str | None = None
    destination_province: str | None = None
    destination_city: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    travel_month: str | None = None
    travel_dates: str | None = None
    travel_days: int | None = None
    travelers: int | None = None
    budget: float | None = None
    currency: str | None = None
    interests: list[str] = Field(default_factory=list)
    travel_style: str | None = None
    special_requirements: list[str] = Field(default_factory=list)

    def apply_update(
        self,
        updates: "TravelRequest",
        *,
        clear_fields: list[str] | None = None,
        remove_items: dict[str, list[Any]] | None = None,
    ) -> "TravelRequest":
        """合并本轮旅行需求，并支持显式清空字段或删除列表项目。"""
        current = self.model_dump()
        for key, value in updates.model_dump().items():
            if value in (None, "", []):
                continue
            if isinstance(value, list):
                current[key] = list(dict.fromkeys([*(current.get(key) or []), *value]))
            else:
                current[key] = value

        for key, values in (remove_items or {}).items():
            if key in type(self).model_fields and isinstance(current.get(key), list):
                current[key] = [item for item in current[key] if item not in values]

        for key in clear_fields or []:
            if key not in type(self).model_fields:
                continue
            annotation = type(self).model_fields[key].annotation
            current[key] = [] if "list" in str(annotation) else None
        return TravelRequest(**current)
