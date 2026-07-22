"""Repository for the marketing_strategies table (one row per consulting case)."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

from domain import Finding, MarketingStrategy, StrategyGenerationReason, StrategyInitiative
from storage.database_connection import open_database_connection
from storage.json_codec import (
    deserialize_json_to_model_list,
    deserialize_json_to_string_list,
    serialize_model_list_to_json,
    serialize_string_list_to_json,
)


def save_marketing_strategy(strategy: MarketingStrategy) -> None:
    """Insert or replace the marketing strategy for this consulting case."""
    with open_database_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO marketing_strategies (
                consulting_case_id, generated_because, executive_summary,
                strategic_objectives, recommended_channels, key_initiatives,
                supporting_findings, override_warning_message, generated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                strategy.consulting_case_id,
                strategy.generated_because.value,
                strategy.executive_summary,
                serialize_string_list_to_json(strategy.strategic_objectives),
                serialize_string_list_to_json(strategy.recommended_channels),
                serialize_model_list_to_json(strategy.key_initiatives),
                serialize_model_list_to_json(strategy.supporting_findings),
                strategy.override_warning_message,
                strategy.generated_at.isoformat(),
            ),
        )


def get_marketing_strategy_by_case_id(case_id: str) -> Optional[MarketingStrategy]:
    with open_database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM marketing_strategies WHERE consulting_case_id = ?", (case_id,)
        ).fetchone()
    return _map_row_to_marketing_strategy(row) if row is not None else None


def _map_row_to_marketing_strategy(row: sqlite3.Row) -> MarketingStrategy:
    return MarketingStrategy(
        consulting_case_id=row["consulting_case_id"],
        generated_because=StrategyGenerationReason(row["generated_because"]),
        executive_summary=row["executive_summary"],
        strategic_objectives=deserialize_json_to_string_list(row["strategic_objectives"]),
        recommended_channels=deserialize_json_to_string_list(row["recommended_channels"]),
        key_initiatives=deserialize_json_to_model_list(row["key_initiatives"], StrategyInitiative),
        supporting_findings=deserialize_json_to_model_list(row["supporting_findings"], Finding),
        override_warning_message=row["override_warning_message"],
        generated_at=datetime.fromisoformat(row["generated_at"]),
    )
