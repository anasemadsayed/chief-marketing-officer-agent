"""Repository for the business_diagnosis table (one row per consulting case)."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

from domain import BusinessDiagnosis, ConfidenceLevel, Finding, MarketingNecessityDecision
from storage.database_connection import open_database_connection
from storage.json_codec import deserialize_json_to_model_list, serialize_model_list_to_json


def save_business_diagnosis(diagnosis: BusinessDiagnosis) -> None:
    """Insert or replace the diagnosis for this consulting case."""
    with open_database_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO business_diagnosis (
                consulting_case_id, decision, primary_bottleneck, reasoning_summary,
                supporting_findings, confidence, diagnosed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                diagnosis.consulting_case_id,
                diagnosis.decision.value,
                diagnosis.primary_bottleneck,
                diagnosis.reasoning_summary,
                serialize_model_list_to_json(diagnosis.supporting_findings),
                diagnosis.confidence.value,
                diagnosis.diagnosed_at.isoformat(),
            ),
        )


def get_business_diagnosis_by_case_id(case_id: str) -> Optional[BusinessDiagnosis]:
    with open_database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM business_diagnosis WHERE consulting_case_id = ?", (case_id,)
        ).fetchone()
    return _map_row_to_business_diagnosis(row) if row is not None else None


def _map_row_to_business_diagnosis(row: sqlite3.Row) -> BusinessDiagnosis:
    return BusinessDiagnosis(
        consulting_case_id=row["consulting_case_id"],
        decision=MarketingNecessityDecision(row["decision"]),
        primary_bottleneck=row["primary_bottleneck"],
        reasoning_summary=row["reasoning_summary"],
        supporting_findings=deserialize_json_to_model_list(row["supporting_findings"], Finding),
        confidence=ConfidenceLevel(row["confidence"]),
        diagnosed_at=datetime.fromisoformat(row["diagnosed_at"]),
    )
