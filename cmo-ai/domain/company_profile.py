"""
CompanyProfile — the stable "who is this company" identity record.

This is distinct from ExtractedCompanyInformation: CompanyProfile holds
simple identity facts (name, industry, location, size, social links),
while ExtractedCompanyInformation holds the cleaned business substance
(products, value proposition, pricing signals, etc.) pulled out of raw
collected content.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class CompanyProfile(BaseModel):
    """Basic, stable identity information about the company being analyzed."""

    consulting_case_id: str

    company_name: str = Field(..., min_length=1)
    industry: Optional[str] = None
    short_description: Optional[str] = Field(
        default=None,
        description="One or two sentence description of what the company does.",
    )

    website_url: Optional[HttpUrl] = None
    linkedin_url: Optional[HttpUrl] = None
    facebook_url: Optional[HttpUrl] = None
    instagram_url: Optional[HttpUrl] = None

    headquarters_location: Optional[str] = None
    founding_year: Optional[int] = Field(default=None, ge=1800, le=2100)
    estimated_company_size_range: Optional[str] = Field(
        default=None,
        description='Free-form bucket, e.g. "1-10", "11-50", "51-200".',
    )

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
