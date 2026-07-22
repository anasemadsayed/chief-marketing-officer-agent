"""
MarketResearch — structured market intelligence for one consulting case.

Produced exclusively by the Market Research Service (Brick 6), using the
small free LLM. The service gathers this information; it never reasons
about what it means for the company's strategy — that is the
orchestrator's job.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class CompetitorProfile(BaseModel):
    """One identified competitor and whatever public information was found."""

    name: str = Field(..., min_length=1)
    website_url: Optional[HttpUrl] = None
    notes: Optional[str] = Field(
        default=None,
        description="Free-form observations, e.g. positioning, pricing, strengths.",
    )


class MarketResearch(BaseModel):
    """Structured competitor, industry, audience, and trend intelligence."""

    consulting_case_id: str

    industry_overview: str = Field(
        default="",
        description="Brief description of the industry the company operates in.",
    )

    competitors: list[CompetitorProfile] = Field(default_factory=list)

    target_audience_characteristics: list[str] = Field(
        default_factory=list,
        description="Market-level audience traits, distinct from the company's own claims.",
    )

    market_trends: list[str] = Field(default_factory=list)

    additional_notes: list[str] = Field(
        default_factory=list,
        description="Any other useful, publicly available business intelligence.",
    )

    researched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
