"""
CollectedSource — one raw, unprocessed piece of collected content.

Produced exclusively by collector services (website, PDF, social media).
Collectors never clean or interpret this content — that is the
Information Extraction Service's job (Brick 7), which reads many
CollectedSource rows and produces one ExtractedCompanyInformation object.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from domain.enums import InformationSourceType


class CollectedSource(BaseModel):
    """A single raw collection result from one source (page, PDF, profile)."""

    id: str = Field(..., description="Unique identifier for this collected item.")
    consulting_case_id: str

    source_type: InformationSourceType
    source_url_or_path: str = Field(
        ..., description="The URL scraped or the local file path processed."
    )

    raw_content: str = Field(
        default="",
        description="Unmodified text extracted from the source. May be long/noisy.",
    )

    collection_successful: bool = True
    collection_error_message: Optional[str] = Field(
        default=None,
        description="Populated when collection_successful is False.",
    )

    collected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
