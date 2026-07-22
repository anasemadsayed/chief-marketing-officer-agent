"""
ExtractedCompanyInformation — the cleaned, structured business substance
pulled out of all CollectedSource rows for one consulting case.

Produced exclusively by the Information Extraction Service (Brick 7),
after the Market Research Service has also run. This is the last object
the orchestrator reads before it starts reasoning — everything in here
should already be noise-free and business-relevant.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ExtractedCompanyInformation(BaseModel):
    """Clean, deduplicated, business-relevant information about the company."""

    consulting_case_id: str

    company_description_summary: str = Field(
        default="",
        description="Short, clean summary of what the company does, in plain language.",
    )

    products_and_services: list[str] = Field(default_factory=list)
    value_proposition: str = Field(
        default="",
        description="What the company claims makes it worth choosing, in its own words.",
    )
    unique_selling_points: list[str] = Field(default_factory=list)

    target_audience_signals: list[str] = Field(
        default_factory=list,
        description="Any explicit or implicit statements about who the company serves.",
    )

    pricing_information: list[str] = Field(
        default_factory=list,
        description="Any pricing, plans, or packaging details found in the raw content.",
    )

    contact_information: list[str] = Field(default_factory=list)

    notable_content_snippets: list[str] = Field(
        default_factory=list,
        description=(
            "Short, meaningful excerpts worth keeping as evidence "
            "(e.g. a mission statement, a customer testimonial)."
        ),
    )

    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
