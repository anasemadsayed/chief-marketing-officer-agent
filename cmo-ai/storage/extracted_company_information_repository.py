"""Repository for the extracted_company_information table (one row per case)."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

from domain import ExtractedCompanyInformation
from storage.database_connection import open_database_connection
from storage.json_codec import deserialize_json_to_string_list, serialize_string_list_to_json


def save_extracted_information(info: ExtractedCompanyInformation) -> None:
    """Insert or replace the cleaned/extracted business information for this case."""
    with open_database_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO extracted_company_information (
                consulting_case_id, company_description_summary, products_and_services,
                value_proposition, unique_selling_points, target_audience_signals,
                pricing_information, contact_information, notable_content_snippets,
                extracted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                info.consulting_case_id,
                info.company_description_summary,
                serialize_string_list_to_json(info.products_and_services),
                info.value_proposition,
                serialize_string_list_to_json(info.unique_selling_points),
                serialize_string_list_to_json(info.target_audience_signals),
                serialize_string_list_to_json(info.pricing_information),
                serialize_string_list_to_json(info.contact_information),
                serialize_string_list_to_json(info.notable_content_snippets),
                info.extracted_at.isoformat(),
            ),
        )


def get_extracted_information_by_case_id(case_id: str) -> Optional[ExtractedCompanyInformation]:
    with open_database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM extracted_company_information WHERE consulting_case_id = ?",
            (case_id,),
        ).fetchone()
    return _map_row_to_extracted_information(row) if row is not None else None


def _map_row_to_extracted_information(row: sqlite3.Row) -> ExtractedCompanyInformation:
    return ExtractedCompanyInformation(
        consulting_case_id=row["consulting_case_id"],
        company_description_summary=row["company_description_summary"],
        products_and_services=deserialize_json_to_string_list(row["products_and_services"]),
        value_proposition=row["value_proposition"],
        unique_selling_points=deserialize_json_to_string_list(row["unique_selling_points"]),
        target_audience_signals=deserialize_json_to_string_list(row["target_audience_signals"]),
        pricing_information=deserialize_json_to_string_list(row["pricing_information"]),
        contact_information=deserialize_json_to_string_list(row["contact_information"]),
        notable_content_snippets=deserialize_json_to_string_list(row["notable_content_snippets"]),
        extracted_at=datetime.fromisoformat(row["extracted_at"]),
    )
