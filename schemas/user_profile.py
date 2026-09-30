from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from schemas.travel_request import TravelRequest

# 定义用户画像的统一数据结构，包含出发城市、目的地、旅行月份、旅行日期、旅行天数、预算、货币、兴趣爱好、旅行风格、避免事项、住宿偏好、饮食偏好、交通偏好、饮食限制、行动不便限制和已访问目的地等信息。
class UserProfile(BaseModel):
    """保存跨旅行长期有效的用户偏好，不保存某一次旅行的目的地和预算。"""

    # 下面字段仅用于兼容旧存档和旧调用，新工作流会把它们写入 TravelRequest。
    departure_city: str | None = Field(default=None, exclude=True)
    destination: str | None = Field(default=None, exclude=True)
    travel_month: str | None = Field(default=None, exclude=True)
    travel_dates: str | None = Field(default=None, exclude=True)
    travel_days: int | None = Field(default=None, exclude=True)
    budget: float | None = Field(default=None, exclude=True)
    currency: str | None = Field(default=None, exclude=True)
    interests: list[str] = Field(default_factory=list)
    travel_style: str | None = None
    avoid: list[str] = Field(default_factory=list)
    accommodation_preference: str | None = None
    food_preference: str | None = None
    transport_preference: str | None = None
    dietary_restrictions: list[str] = Field(default_factory=list)
    mobility_constraints: list[str] = Field(default_factory=list)
    visited_destinations: list[str] = Field(default_factory=list)

    def merge_non_empty(self, updates: "UserProfile") -> "UserProfile":
        """合并非空画像字段，并对列表字段去重且保留原顺序。"""
        current = self.model_dump() # 获取当前对象的字典表示
        incoming = updates.model_dump() # 获取更新对象的字典表示

        for key, value in incoming.items():
            if value is None or value == "":
                continue

            if isinstance(value, list):
                if not value:
                    continue
                existing = current.get(key) or []
                current[key] = list(dict.fromkeys([*existing, *value])) # 去重且保留顺序
                continue

            current[key] = value

        return UserProfile(**current)

    def apply_update(
        self,
        updates: "UserProfile",
        *,
        clear_fields: list[str] | None = None,
        remove_items: dict[str, list[Any]] | None = None,
    ) -> "UserProfile":
        """更新长期偏好，并支持显式清空字段和删除列表中的旧偏好。"""
        merged = self.merge_non_empty(updates).model_dump()
        for key, values in (remove_items or {}).items():
            if key in type(self).model_fields and isinstance(merged.get(key), list):
                merged[key] = [item for item in merged[key] if item not in values]
        for key in clear_fields or []:
            if key not in type(self).model_fields:
                continue
            annotation = type(self).model_fields[key].annotation
            merged[key] = [] if "list" in str(annotation) else None
        return UserProfile(**merged)

    @classmethod
    def from_partial_dict(cls, data: dict[str, Any]) -> "UserProfile":
        """过滤未知字段，并根据部分字典创建用户画像。"""
        allowed = cls.model_fields.keys()
        return cls(**{key: value for key, value in data.items() if key in allowed}) # **解包字典并传递给构造函数


class ProfileExtraction(BaseModel):
    """描述一轮对话对长期画像、当前旅行和长期记忆分别产生的增量更新。"""

    profile_updates: UserProfile = Field(default_factory=UserProfile)
    trip_updates: TravelRequest = Field(default_factory=TravelRequest)
    clear_profile_fields: list[str] = Field(default_factory=list)
    clear_trip_fields: list[str] = Field(default_factory=list)
    remove_profile_items: dict[str, list[Any]] = Field(default_factory=dict)
    remove_trip_items: dict[str, list[Any]] = Field(default_factory=dict)
    start_new_trip: bool = False
    memory_candidates: list[dict[str, Any]] = Field(default_factory=list)
    memory_extraction_status: str = "completed"
