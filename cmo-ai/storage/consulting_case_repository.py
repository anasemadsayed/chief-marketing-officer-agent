"""
Repository for the consulting_cases table.

This is the entry point of the whole storage layer: every other table
references a row created here.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from domain import ConsultingCase, ConsultingCaseStatus
from storage.database_connection import open_database_connection
from storage.id_generator import generate_unique_consulting_case_id
from storage.json_codec import (
    deserialize_json_to_string_list,
    serialize_string_list_to_json,
    url_or_none_to_str,
)


def create_consulting_case(
    company_name: str,
    website_url: Optional[str] = None,
    pdf_file_path: Optional[str] = None,
    linkedin_url: Optional[str] = None,
    facebook_url: Optional[str] = None,
    instagram_url: Optional[str] = None,
    additional_links: Optional[list[str]] = None,
) -> ConsultingCase:
    """Create a brand-new consulting case with a guaranteed-unique id and persist it."""
    case = ConsultingCase(
        id=generate_unique_consulting_case_id(company_name),
        company_name=company_name,
        website_url=website_url,
        pdf_file_path=pdf_file_path,
        linkedin_url=linkedin_url,
        facebook_url=facebook_url,
        instagram_url=instagram_url,
        additional_links=additional_links or [],
    )
    with open_database_connection() as connection:
        connection.execute(
            """
            INSERT INTO consulting_cases (
                id, company_name, status, website_url, pdf_file_path,
                linkedin_url, facebook_url, instagram_url, additional_links,
                failure_reason, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case.id,
                case.company_name,
                case.status.value,
                url_or_none_to_str(case.website_url),
                case.pdf_file_path,
                url_or_none_to_str(case.linkedin_url),
                url_or_none_to_str(case.facebook_url),
                url_or_none_to_str(case.instagram_url),
                serialize_string_list_to_json([str(link) for link in case.additional_links]),
                case.failure_reason,
                case.created_at.isoformat(),
                case.updated_at.isoformat(),
            ),
        )
    return case


def get_consulting_case_by_id(case_id: str) -> Optional[ConsultingCase]:
    with open_database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM consulting_cases WHERE id = ?", (case_id,)
        ).fetchone()
    return _map_row_to_consulting_case(row) if row is not None else None


def update_consulting_case_status(
    case_id: str,
    status: ConsultingCaseStatus,
    failure_reason: Optional[str] = None,
) -> None:
    with open_database_connection() as connection:
        connection.execute(
            "UPDATE consulting_cases SET status = ?, failure_reason = ?, updated_at = ? WHERE id = ?",
            (status.value, failure_reason, datetime.now(timezone.utc).isoformat(), case_id),
        )


def list_all_consulting_cases() -> list[ConsultingCase]:
    with open_database_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM consulting_cases ORDER BY created_at DESC"
        ).fetchall()
    return [_map_row_to_consulting_case(row) for row in rows]


def _map_row_to_consulting_case(row: sqlite3.Row) -> ConsultingCase:
    return ConsultingCase(
        id=row["id"],
        company_name=row["company_name"],
        status=ConsultingCaseStatus(row["status"]),
        website_url=row["website_url"],
        pdf_file_path=row["pdf_file_path"],
        linkedin_url=row["linkedin_url"],
        facebook_url=row["facebook_url"],
        instagram_url=row["instagram_url"],
        additional_links=deserialize_json_to_string_list(row["additional_links"]),
        failure_reason=row["failure_reason"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )
