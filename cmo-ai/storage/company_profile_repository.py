"""Repository for the company_profiles table (one row per consulting case)."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

from domain import CompanyProfile
from storage.database_connection import open_database_connection
from storage.json_codec import url_or_none_to_str


def save_company_profile(profile: CompanyProfile) -> None:
    """Insert or replace the company profile for this consulting case."""
    with open_database_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO company_profiles (
                consulting_case_id, company_name, industry, short_description,
                website_url, linkedin_url, facebook_url, instagram_url,
                headquarters_location, founding_year, estimated_company_size_range,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile.consulting_case_id,
                profile.company_name,
                profile.industry,
                profile.short_description,
                url_or_none_to_str(profile.website_url),
                url_or_none_to_str(profile.linkedin_url),
                url_or_none_to_str(profile.facebook_url),
                url_or_none_to_str(profile.instagram_url),
                profile.headquarters_location,
                profile.founding_year,
                profile.estimated_company_size_range,
                profile.created_at.isoformat(),
            ),
        )


def get_company_profile_by_case_id(case_id: str) -> Optional[CompanyProfile]:
    with open_database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM company_profiles WHERE consulting_case_id = ?", (case_id,)
        ).fetchone()
    return _map_row_to_company_profile(row) if row is not None else None


def _map_row_to_company_profile(row: sqlite3.Row) -> CompanyProfile:
    return CompanyProfile(
        consulting_case_id=row["consulting_case_id"],
        company_name=row["company_name"],
        industry=row["industry"],
        short_description=row["short_description"],
        website_url=row["website_url"],
        linkedin_url=row["linkedin_url"],
        facebook_url=row["facebook_url"],
        instagram_url=row["instagram_url"],
        headquarters_location=row["headquarters_location"],
        founding_year=row["founding_year"],
        estimated_company_size_range=row["estimated_company_size_range"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )
