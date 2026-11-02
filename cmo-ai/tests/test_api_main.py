"""
Tests for the HTTP API (Brick 11, Part 2).

The pipeline functions themselves are monkeypatched at the names as
imported into api.main's namespace, so these tests verify HTTP
concerns — status codes, request validation, response shapes, and
error-to-status-code mapping — without re-exercising the pipeline's own
internals (already covered by test_consulting_pipeline.py) or making
any real network/LLM calls.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import main as api_main
from api.consulting_pipeline import ConsultingPipelineError
from domain import (
    BusinessDiagnosis,
    ConfidenceLevel,
    GeneratedReport,
    MarketingNecessityDecision,
    MarketingStrategy,
    ReportType,
    StrategyGenerationReason,
)
from orchestrator.errors import OrchestratorError
from storage.business_diagnosis_repository import save_business_diagnosis
from storage.consulting_case_repository import create_consulting_case
from storage.generated_report_repository import save_generated_report


@pytest.fixture()
def test_client(isolated_test_database):
    with TestClient(api_main.app, raise_server_exceptions=False) as client:
        yield client


def _make_report(case_id: str, with_strategy: bool = False) -> GeneratedReport:
    diagnosis = BusinessDiagnosis(
        consulting_case_id=case_id,
        decision=(
            MarketingNecessityDecision.MARKETING_IS_THE_PRIMARY_ISSUE
            if with_strategy
            else MarketingNecessityDecision.MARKETING_IS_NOT_THE_PRIMARY_ISSUE
        ),
        primary_bottleneck="Some bottleneck.",
        reasoning_summary="Some reasoning.",
        confidence=ConfidenceLevel.MEDIUM,
    )
    strategy = None
    if with_strategy:
        strategy = MarketingStrategy(
            consulting_case_id=case_id,
            generated_because=StrategyGenerationReason.DIAGNOSIS_RECOMMENDED_MARKETING,
            executive_summary="A strategy.",
        )
    return GeneratedReport(
        consulting_case_id=case_id,
        report_type=ReportType.DIAGNOSIS_AND_STRATEGY if with_strategy else ReportType.DIAGNOSIS_ONLY,
        diagnosis=diagnosis,
        strategy=strategy,
    )


def _make_and_save_report(case_id: str, with_strategy: bool = False) -> GeneratedReport:
    """
    Like _make_report, but also persists the diagnosis first, matching
    what save_generated_report requires (see
    generated_report_repository's data-integrity check).
    """
    report = _make_report(case_id, with_strategy=with_strategy)
    save_business_diagnosis(report.diagnosis)
    save_generated_report(report)
    return report


def test_health_check(test_client):
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_endpoint(test_client):
    response = test_client.get("/")
    assert response.status_code == 200
    assert response.json()["name"] == "cmoAI"


def test_create_consulting_case_success(test_client, monkeypatch):
    fake_report = _make_report("acme-001")
    monkeypatch.setattr(api_main, "run_consulting_case_analysis_pipeline", lambda **kw: fake_report)

    response = test_client.post(
        "/consulting-cases",
        json={"company_name": "Acme Corp", "website_url": "https://acme.example.com"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["consulting_case_id"] == "acme-001"
    assert body["report_type"] == "diagnosis_only"


def test_create_consulting_case_rejects_missing_company_name(test_client):
    response = test_client.post("/consulting-cases", json={"website_url": "https://acme.example.com"})
    assert response.status_code == 422


def test_create_consulting_case_rejects_malformed_url(test_client):
    response = test_client.post(
        "/consulting-cases", json={"company_name": "Acme Corp", "website_url": "not-a-url"}
    )
    assert response.status_code == 422


def test_create_consulting_case_maps_pipeline_error_to_400(test_client, monkeypatch):
    def fake_raise(**kw):
        raise ConsultingPipelineError("no input source was provided")

    monkeypatch.setattr(api_main, "run_consulting_case_analysis_pipeline", fake_raise)

    response = test_client.post("/consulting-cases", json={"company_name": "Ghost Co"})

    assert response.status_code == 400
    assert "no input source" in response.json()["detail"]


def test_create_consulting_case_maps_orchestrator_error_to_502(test_client, monkeypatch):
    def fake_raise(**kw):
        raise OrchestratorError("Could not generate a business diagnosis: LLM unavailable")

    monkeypatch.setattr(api_main, "run_consulting_case_analysis_pipeline", fake_raise)

    response = test_client.post(
        "/consulting-cases", json={"company_name": "Acme Corp", "website_url": "https://acme.example.com"}
    )

    assert response.status_code == 502
    assert "LLM unavailable" in response.json()["detail"]


def test_create_consulting_case_maps_unexpected_error_to_500(test_client, monkeypatch):
    def fake_raise(**kw):
        raise RuntimeError("something truly unexpected")

    monkeypatch.setattr(api_main, "run_consulting_case_analysis_pipeline", fake_raise)

    response = test_client.post(
        "/consulting-cases", json={"company_name": "Acme Corp", "website_url": "https://acme.example.com"}
    )

    assert response.status_code == 500
    # Detail is deliberately generic — the real error is logged, not leaked to the client.
    assert response.json()["detail"] == "An unexpected error occurred."


def test_get_consulting_case_not_found(test_client):
    response = test_client.get("/consulting-cases/does-not-exist")
    assert response.status_code == 404


def test_get_consulting_case_found(test_client):
    case = create_consulting_case(company_name="Acme Corp", website_url="https://acme.example.com")

    response = test_client.get(f"/consulting-cases/{case.id}")

    assert response.status_code == 200
    assert response.json()["company_name"] == "Acme Corp"


def test_list_consulting_cases(test_client):
    create_consulting_case(company_name="Acme Corp")
    create_consulting_case(company_name="Beta Inc")

    response = test_client.get("/consulting-cases")

    assert response.status_code == 200
    names = {case["company_name"] for case in response.json()}
    assert names == {"Acme Corp", "Beta Inc"}


def test_get_report_not_found(test_client):
    case = create_consulting_case(company_name="Acme Corp")
    response = test_client.get(f"/consulting-cases/{case.id}/report")
    assert response.status_code == 404


def test_get_report_found(test_client):
    case = create_consulting_case(company_name="Acme Corp")
    _make_and_save_report(case.id)

    response = test_client.get(f"/consulting-cases/{case.id}/report")

    assert response.status_code == 200
    assert response.json()["report_type"] == "diagnosis_only"


def test_generate_strategy_anyway_case_not_found(test_client):
    response = test_client.post("/consulting-cases/does-not-exist/generate-strategy-anyway")
    assert response.status_code == 404


def test_generate_strategy_anyway_success(test_client, monkeypatch):
    case = create_consulting_case(company_name="Acme Corp")
    updated_report = _make_report(case.id, with_strategy=True)

    monkeypatch.setattr(
        api_main, "generate_marketing_strategy_report_for_existing_case",
        lambda case_id, company_name: updated_report,
    )

    response = test_client.post(f"/consulting-cases/{case.id}/generate-strategy-anyway")

    assert response.status_code == 200
    assert response.json()["report_type"] == "diagnosis_and_strategy"


def test_generate_strategy_anyway_maps_orchestrator_error_to_502(test_client, monkeypatch):
    case = create_consulting_case(company_name="Acme Corp")

    def fake_raise(case_id, company_name):
        raise OrchestratorError("diagnosis already recommended marketing")

    monkeypatch.setattr(api_main, "generate_marketing_strategy_report_for_existing_case", fake_raise)

    response = test_client.post(f"/consulting-cases/{case.id}/generate-strategy-anyway")

    assert response.status_code == 502
    assert "already recommended marketing" in response.json()["detail"]


def test_download_pptx_not_found_when_no_report(test_client):
    case = create_consulting_case(company_name="Acme Corp")
    response = test_client.get(f"/consulting-cases/{case.id}/download-pptx")
    assert response.status_code == 404


def test_download_pptx_not_found_when_file_missing_on_disk(test_client):
    case = create_consulting_case(company_name="Acme Corp")
    report = _make_and_save_report(case.id)
    report = report.model_copy(update={"powerpoint_file_path": "/tmp/does-not-exist-12345.pptx"})
    save_generated_report(report)

    response = test_client.get(f"/consulting-cases/{case.id}/download-pptx")
    assert response.status_code == 404


def test_download_pptx_success(test_client, tmp_path):
    case = create_consulting_case(company_name="Acme Corp")
    pptx_path = tmp_path / "report.pptx"
    pptx_path.write_bytes(b"fake pptx bytes")

    report = _make_and_save_report(case.id)
    report = report.model_copy(update={"powerpoint_file_path": str(pptx_path)})
    save_generated_report(report)

    response = test_client.get(f"/consulting-cases/{case.id}/download-pptx")

    assert response.status_code == 200
    assert response.content == b"fake pptx bytes"
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    )
