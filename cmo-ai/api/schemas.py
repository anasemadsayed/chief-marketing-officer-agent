"""
Request schemas for the HTTP API (Brick 11, Part 2).

Response bodies reuse the domain models directly (ConsultingCase,
GeneratedReport, etc.) rather than a separate DTO layer — they're
already Pydantic models with exactly the shape a client needs, and V1's
API surface is simple enough that duplicating schemas would only add
maintenance risk without adding clarity.

URL fields use HttpUrl (not plain str) so FastAPI's own request
validation rejects a malformed URL with a clean 422 before any pipeline
code ever runs.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class CreateConsultingCaseRequest(BaseModel):
    """Request body for POST /consulting-cases."""

    company_name: str = Field(..., min_length=1)
    website_url: Optional[HttpUrl] = None
    pdf_file_path: Optional[str] = Field(
        default=None,
        description=(
            "Absolute path to a PDF already accessible on the server's filesystem. "
            "V1 has no file-upload endpoint, so the file must already exist there."
        ),
    )
    linkedin_url: Optional[HttpUrl] = None
    facebook_url: Optional[HttpUrl] = None
    instagram_url: Optional[HttpUrl] = None
    additional_links: list[HttpUrl] = Field(default_factory=list)
