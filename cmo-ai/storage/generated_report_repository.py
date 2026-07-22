"""
Repository for the generated_reports table (one row per consulting case).

This table only stores the report's own fields (type, PowerPoint path,
timestamp) — the diagnosis and strategy it wraps already live in their
own tables (business_diagnosis, marketing_strategies) and are re-attached
here on read. This avoids duplicating that data in a third place.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

from domain import GeneratedReport, ReportType
from storage.business_diagnosis_repository import get_business_diagnosis_by_case_id
from storage.database_connection import open_database_connection
from storage.marketing_strategy_repository import get_marketing_strategy_by_case_id


def save_generated_report(report: GeneratedReport) -> None:
    """
    Insert or replace the report row for this consulting case.

    Assumes `report.diagnosis` (and `report.strategy`, if present) have
    already been persisted via their own repositories — this call only
    saves the report-level metadata.
    """
    with open_database_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO generated_reports (
                consulting_case_id, report_type, powerpoint_file_path, generated_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                report.consulting_case_id,
                report.report_type.value,
                report.powerpoint_file_path,
                report.generated_at.isoformat(),
            ),
        )


def get_generated_report_by_case_id(case_id: str) -> Optional[GeneratedReport]:
    """
    Reconstruct the full GeneratedReport, pulling its diagnosis (and
    strategy, if any) back in from their own tables.
    """
    with open_database_connection() as connection:
        row = connection.execute(
            "SELECT * FROM generated_reports WHERE consulting_case_id = ?", (case_id,)
        ).fetchone()
    if row is None:
        return None

    diagnosis = get_business_diagnosis_by_case_id(case_id)
    if diagnosis is None:
        raise ValueError(
            f"generated_reports row exists for case '{case_id}' but its "
            "business_diagnosis row is missing — data integrity issue."
        )

    report_type = ReportType(row["report_type"])
    strategy = (
        get_marketing_strategy_by_case_id(case_id)
        if report_type == ReportType.DIAGNOSIS_AND_STRATEGY
        else None
    )

    return GeneratedReport(
        consulting_case_id=row["consulting_case_id"],
        report_type=report_type,
        diagnosis=diagnosis,
        strategy=strategy,
        powerpoint_file_path=row["powerpoint_file_path"],
        generated_at=datetime.fromisoformat(row["generated_at"]),
    )
