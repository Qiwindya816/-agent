"""Schemas for explainable personalized recommendation ranking."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RankingFeature(BaseModel):
    """One normalized feature and its contribution to the final score."""

    name: str
    value: float
    weight: float
    contribution: float
    explanation: str


class RankedActivity(BaseModel):
    """A ranked candidate with an explainable score."""

    activity_id: str | None = None
    name: str
    score: float
    rank: int
    features: list[RankingFeature] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    rejected_by_memory: bool = False
