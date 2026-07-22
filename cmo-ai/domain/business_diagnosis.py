"""
BusinessDiagnosis — the orchestrator's root-cause decision for one case.

This is the single most important object in the system: it is where the
orchestrator decides whether marketing is actually the company's problem,
and states the real bottleneck if it isn't. Everything downstream
(strategy generation or diagnosis-only report) is driven by this object.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from domain.enums import ConfidenceLevel, MarketingNecessityDecision
from domain.finding import Finding


class BusinessDiagnosis(BaseModel):
    """The orchestrator's evidence-backed diagnosis of the company's real problem."""

    consulting_case_id: str

    decision: MarketingNecessityDecision

    primary_bottleneck: str = Field(
        ...,
        min_length=1,
        description=(
            "The actual root cause in plain language, whether or not it is "
            "marketing (e.g. 'pricing misaligned with perceived value', "
            "'weak product-market fit', 'high website drop-off at checkout')."
        ),
    )

    reasoning_summary: str = Field(
        ...,
        min_length=1,
        description="Plain-language explanation of how the orchestrator reached this decision.",
    )

    supporting_findings: list[Finding] = Field(
        default_factory=list,
        description="Evidence backing the diagnosis. Should not be empty in practice.",
    )

    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM

    diagnosed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def marketing_is_recommended(self) -> bool:
        """Convenience check used by the flow-control logic in later bricks."""
        return self.decision == MarketingNecessityDecision.MARKETING_IS_THE_PRIMARY_ISSUE
