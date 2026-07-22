"""
GeneratedReport — the final deliverable returned to the user for one case.

Always wraps a BusinessDiagnosis. Wraps a MarketingStrategy too, but only
when one was actually generated (diagnosis said yes, or the user
overrode a "no" diagnosis).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from domain.business_diagnosis import BusinessDiagnosis
from domain.enums import ReportType
from domain.marketing_strategy import MarketingStrategy


class GeneratedReport(BaseModel):
    """The final report (and optional PowerPoint) produced for a consulting case."""

    consulting_case_id: str

    report_type: ReportType

    diagnosis: BusinessDiagnosis
    strategy: Optional[MarketingStrategy] = None

    powerpoint_file_path: Optional[str] = Field(
        default=None,
        description="Set once the PowerPoint Generator service (Brick 10) has run.",
    )

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def ensure_strategy_matches_report_type(self) -> "GeneratedReport":
        """Keep report_type and the presence/absence of a strategy in sync."""
        if self.report_type == ReportType.DIAGNOSIS_AND_STRATEGY and self.strategy is None:
            raise ValueError(
                "report_type is DIAGNOSIS_AND_STRATEGY but no strategy was provided."
            )
        if self.report_type == ReportType.DIAGNOSIS_ONLY and self.strategy is not None:
            raise ValueError(
                "report_type is DIAGNOSIS_ONLY but a strategy was provided."
            )
        return self
