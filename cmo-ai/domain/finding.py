"""
Finding — a single evidence-backed observation.

Findings are the atomic unit of "proof" in cmoAI. Both BusinessDiagnosis
and MarketingStrategy are built out of lists of Findings, which is what
lets the system honor design principle #7: every recommendation must be
supported by evidence.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from domain.enums import ConfidenceLevel


class Finding(BaseModel):
    """One discrete, evidence-backed observation used to support a decision."""

    description: str = Field(
        ..., min_length=1, description="The observation itself, stated plainly."
    )

    evidence: str = Field(
        ...,
        min_length=1,
        description="The concrete evidence backing this observation (a quote, a data point).",
    )

    source_reference: str = Field(
        default="",
        description=(
            'Where the evidence came from, e.g. "company_website:about_page", '
            '"market_research:competitor_analysis".'
        ),
    )

    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
