"""Repository for the market_research table (one row per consulting case)."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

from domain import CompetitorProfile, MarketResearch
from storage.database_connection import open_database_connection
from storage.json_codec import (
    deserialize_json_to_model_list,
    deserialize_json_to_string_list,
    serialize_model_list_to_json,
    serialize_string_list_to_json,
)


def save_market_research(research: MarketResearch) -> None:
    """Insert or replace the market research results for this consulting case."""
    with open_database_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO market_research (
                consulting_case_id, industry_overview, competitors,
                target_audience_characteristics, market_trends, additional_notes,
                researched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                research.consulting_case_id,
                research.industry_overview,
                serialize_model_list_to_json(research.competitors),
                serialize_string_list_to_json(research.target_audience_characteristics),
                serialize_string_list_to_json(research.market_trends),
                serialize_string_list_to_json(research.additional_notes),
                research.researched_at.isoformat(),
            ),
        )


def get_market_research_by_case_id(case_id: str) -> Optional[MarketResearch]:
    with open_database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM market_research WHERE consulting_case_id = ?", (case_id,)
        ).fetchone()
    return _map_row_to_market_research(row) if row is not None else None


def _map_row_to_market_research(row: sqlite3.Row) -> MarketResearch:
    return MarketResearch(
        consulting_case_id=row["consulting_case_id"],
        industry_overview=row["industry_overview"],
        competitors=deserialize_json_to_model_list(row["competitors"], CompetitorProfile),
        target_audience_characteristics=deserialize_json_to_string_list(
            row["target_audience_characteristics"]
        ),
        market_trends=deserialize_json_to_string_list(row["market_trends"]),
        additional_notes=deserialize_json_to_string_list(row["additional_notes"]),
        researched_at=datetime.fromisoformat(row["researched_at"]),
    )
