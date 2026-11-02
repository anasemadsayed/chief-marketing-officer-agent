"""
api
===

Application entrypoints for cmoAI.

- consulting_pipeline.py  -> the end-to-end flow wiring every prior
                              brick together (Brick 11, Part 1). Plain
                              Python, no HTTP framework involved — fully
                              testable on its own.
- schemas.py              -> request-body schemas for the HTTP API.
- main.py                 -> the HTTP API (Brick 11, Part 2) exposing
                              consulting_pipeline's two entry points
                              over FastAPI. Run with:
                                  uvicorn api.main:app --reload

Contains no business logic itself: consulting_pipeline.py only
sequences calls to services/orchestrator/storage and manages
ConsultingCase status transitions, and main.py only translates HTTP
requests into those calls and results (or failures) into HTTP
responses. That decision-making responsibility stays exclusively with
the orchestrator.

This is the last brick of cmoAI V1 — every step from the original spec
(collect -> research -> extract -> diagnose -> decide -> strategize/
report -> export) is now wired end-to-end and reachable over HTTP.
"""

from api.consulting_pipeline import (
    ConsultingPipelineError,
    collect_company_information_from_all_sources,
    generate_marketing_strategy_report_for_existing_case,
    run_consulting_case_analysis_pipeline,
)

__all__ = [
    "ConsultingPipelineError",
    "collect_company_information_from_all_sources",
    "generate_marketing_strategy_report_for_existing_case",
    "run_consulting_case_analysis_pipeline",
]
