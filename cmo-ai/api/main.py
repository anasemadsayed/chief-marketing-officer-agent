"""
HTTP API (Brick 11, Part 2) — the last piece of cmoAI V1.

Thin FastAPI wrapper around api.consulting_pipeline's two entry points.
Contains no business logic: every route either reads from storage
directly or delegates to the pipeline/orchestrator, and translates the
result (or failure) into an HTTP response.

Error mapping:
- ConsultingPipelineError (client-side problem, e.g. no input source)  -> 400
- OrchestratorError (the AI reasoning/generation step itself failed)   -> 502
- Anything else unexpected                                              -> 500, logged, detail withheld

Routes are defined as plain `def` (not `async def`) since every
underlying call (requests, sqlite3, python-pptx, the Gemini SDK) is
blocking; FastAPI runs sync route handlers in a thread pool automatically,
so this doesn't block the event loop for other requests.

Run directly with `python -m api.main`, or in production with:
    uvicorn api.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.consulting_pipeline import (
    ConsultingPipelineError,
    generate_marketing_strategy_report_for_existing_case,
    run_consulting_case_analysis_pipeline,
)
from api.schemas import CreateConsultingCaseRequest
from config.logging_config import configure_application_logging
from config.settings import settings
from domain import ConsultingCase, GeneratedReport
from orchestrator.errors import OrchestratorError
from storage import (
    get_consulting_case_by_id,
    get_generated_report_by_case_id,
    initialize_database_schema,
    list_all_consulting_cases,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_application_logging()
    initialize_database_schema()
    logger.info("cmoAI API starting up")
    yield
    logger.info("cmoAI API shutting down")


app = FastAPI(
    title="cmoAI",
    description="AI Business Consultant API — diagnoses a company's real growth "
    "bottleneck and, only when marketing is genuinely the correct lever, "
    "generates an evidence-based marketing strategy and PowerPoint presentation.",
    version="1.0.0",
    lifespan=lifespan,
)

# Resolve the static directory relative to this file's location so the app
# works regardless of the working directory it is launched from.
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.exception_handler(ConsultingPipelineError)
async def handle_consulting_pipeline_error(request: Request, exc: ConsultingPipelineError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(OrchestratorError)
async def handle_orchestrator_error(request: Request, exc: OrchestratorError) -> JSONResponse:
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception while processing %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred."})


@app.get("/", include_in_schema=False)
def read_root() -> FileResponse:
    """Serve the cmoAI frontend UI."""
    return FileResponse(str(_STATIC_DIR / "index.html"))


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@app.post("/consulting-cases", response_model=GeneratedReport, status_code=201)
def create_and_analyze_consulting_case(request: CreateConsultingCaseRequest) -> GeneratedReport:
    """
    Create a new consulting case and run the full V1 pipeline
    synchronously: collect sources, research the market, extract clean
    information, diagnose the business, and generate the appropriate
    report (with PowerPoint) — automatically including a marketing
    strategy only if the diagnosis recommends it.

    This can take a while (web scraping + several LLM calls) since V1
    has no background task queue by design; the response is the
    finished report.
    """
    return run_consulting_case_analysis_pipeline(
        company_name=request.company_name,
        website_url=str(request.website_url) if request.website_url else None,
        pdf_file_path=request.pdf_file_path,
        linkedin_url=str(request.linkedin_url) if request.linkedin_url else None,
        facebook_url=str(request.facebook_url) if request.facebook_url else None,
        instagram_url=str(request.instagram_url) if request.instagram_url else None,
        additional_links=[str(link) for link in request.additional_links],
    )


@app.get("/consulting-cases", response_model=list[ConsultingCase])
def list_consulting_cases() -> list[ConsultingCase]:
    return list_all_consulting_cases()


@app.get("/consulting-cases/{case_id}", response_model=ConsultingCase)
def get_consulting_case(case_id: str) -> ConsultingCase:
    case = get_consulting_case_by_id(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Consulting case '{case_id}' not found.")
    return case


@app.get("/consulting-cases/{case_id}/report", response_model=GeneratedReport)
def get_consulting_case_report(case_id: str) -> GeneratedReport:
    report = get_generated_report_by_case_id(case_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No report found for consulting case '{case_id}'.")
    return report


@app.post("/consulting-cases/{case_id}/generate-strategy-anyway", response_model=GeneratedReport)
def generate_strategy_anyway(case_id: str) -> GeneratedReport:
    """
    The explicit user override: generate a marketing strategy even
    though the diagnosis said marketing was not the primary issue.
    Regenerates the PowerPoint too, since the earlier diagnosis-only
    deck is now out of date.
    """
    case = get_consulting_case_by_id(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Consulting case '{case_id}' not found.")

    return generate_marketing_strategy_report_for_existing_case(case_id, case.company_name)


@app.get("/consulting-cases/{case_id}/download-pptx")
def download_consulting_case_presentation(case_id: str) -> FileResponse:
    report = get_generated_report_by_case_id(case_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No report found for consulting case '{case_id}'.")

    if not report.powerpoint_file_path or not os.path.exists(report.powerpoint_file_path):
        raise HTTPException(status_code=404, detail="No PowerPoint file is available for this report.")

    return FileResponse(
        path=report.powerpoint_file_path,
        filename=os.path.basename(report.powerpoint_file_path),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=(settings.app_env == "development"),
    )
