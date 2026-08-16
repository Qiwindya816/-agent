from pydantic import BaseModel, Field


class Activity(BaseModel):
    name: str
    category: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    location: str | None = None
    estimated_cost: float | None = None
    transport_method: str | None = None
    notes: str | None = None


class DailyItinerary(BaseModel):
    day: int
    date: str | None = None
    theme: str | None = None
    activities: list[Activity] = Field(default_factory=list)
    estimated_daily_cost: float | None = None


class Itinerary(BaseModel):
    destination: str | None = None
    travel_days: int | None = None
    currency: str = "CNY"
    days: list[DailyItinerary] = Field(default_factory=list)
    total_estimated_cost: float | None = None
    assumptions: list[str] = Field(default_factory=list)
