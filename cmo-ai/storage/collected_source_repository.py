"""Repository for the collected_sources table (many rows per consulting case)."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

from domain import CollectedSource, InformationSourceType
from storage.database_connection import open_database_connection
from storage.id_generator import generate_unique_record_id


def save_collected_source(source: CollectedSource) -> None:
    """Insert or replace one collected source row."""
    with open_database_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO collected_sources (
                id, consulting_case_id, source_type, source_url_or_path,
                raw_content, collection_successful, collection_error_message,
                collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source.id,
                source.consulting_case_id,
                source.source_type.value,
                source.source_url_or_path,
                source.raw_content,
                int(source.collection_successful),
                source.collection_error_message,
                source.collected_at.isoformat(),
            ),
        )


def create_and_save_collected_source(
    consulting_case_id: str,
    source_type: InformationSourceType,
    source_url_or_path: str,
    raw_content: str = "",
    collection_successful: bool = True,
    collection_error_message: Optional[str] = None,
) -> CollectedSource:
    """Convenience helper: build a CollectedSource with a fresh id, save it, return it."""
    source = CollectedSource(
        id=generate_unique_record_id("src"),
        consulting_case_id=consulting_case_id,
        source_type=source_type,
        source_url_or_path=source_url_or_path,
        raw_content=raw_content,
        collection_successful=collection_successful,
        collection_error_message=collection_error_message,
    )
    save_collected_source(source)
    return source


def list_collected_sources_for_case(case_id: str) -> list[CollectedSource]:
    with open_database_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM collected_sources WHERE consulting_case_id = ? ORDER BY collected_at ASC",
            (case_id,),
        ).fetchall()
    return [_map_row_to_collected_source(row) for row in rows]


def _map_row_to_collected_source(row: sqlite3.Row) -> CollectedSource:
    return CollectedSource(
        id=row["id"],
        consulting_case_id=row["consulting_case_id"],
        source_type=InformationSourceType(row["source_type"]),
        source_url_or_path=row["source_url_or_path"],
        raw_content=row["raw_content"],
        collection_successful=bool(row["collection_successful"]),
        collection_error_message=row["collection_error_message"],
        collected_at=datetime.fromisoformat(row["collected_at"]),
    )
