"""
Tests for the consulting pipeline (Brick 11, Part 1).

Every underlying service/orchestrator call is monkeypatched at the name
as imported into api.consulting_pipeline's own namespace (the same
pattern used throughout this project), so these tests verify
orchestration logic — sequencing, status transitions, branching,
failure handling — without re-exercising each service's own internals
(already covered by their dedicated test files) or making any real
network/LLM calls.
"""

from __future__ import annotations

import pytest

from api import consulting_pipeline as pipeline
from api.consulting_pipeline import ConsultingPipelineError
from domain import (
    BusinessDiagnosis,
    CollectedSource,
    ConfidenceLevel,
    ConsultingCaseStatus,
    GeneratedReport,
    InformationSourceType,
    MarketingNecessityDecision,
    MarketingStrategy,
    ReportType,
    StrategyGenerationReason,
)
from orchestrator.errors import OrchestratorError
from storage.consulting_case_repository import get_consulting_case_by_id


def _make_source(consulting_case_id: str, text: str = "raw content") -> CollectedSource:
    return CollectedSource(
        id=f"src-{hash(text) % 100000}",
        consulting_case_id=consulting_case_id,
        source_type=InformationSourceType.COMPANY_WEBSITE,
        source_url_or_path="https://acme.example.com",
        raw_content=text,
    )


def _make_diagnosis(case_id: str, recommend_marketing: bool) -> BusinessDiagnosis:
    return BusinessDiagnosis(
        consulting_case_id=case_id,
        decision=(
            MarketingNecessityDecision.MARKETING_IS_THE_PRIMARY_ISSUE
            if recommend_marketing
            else MarketingNecessityDecision.MARKETING_IS_NOT_THE_PRIMARY_ISSUE
        ),
        primary_bottleneck="Some bottleneck.",
        reasoning_summary="Some reasoning.",
        confidence=ConfidenceLevel.MEDIUM,
    )


def _patch_common_pipeline_steps(monkeypatch, case_id_holder: dict, recommend_marketing: bool):
    """Patch every external call the pipeline makes, recording the case id as it becomes known."""

    def fake_collect_website(consulting_case_id, website_url, max_pages=None):
        case_id_holder["id"] = consulting_case_id
        return [_make_source(consulting_case_id)]

    monkeypatch.setattr(pipeline, "collect_website_content_for_consulting_case", fake_collect_website)
    monkeypatch.setattr(pipeline, "collect_pdf_content_for_consulting_case", lambda **kw: _make_source(kw["consulting_case_id"]))
    monkeypatch.setattr(pipeline, "collect_social_media_profiles_for_consulting_case", lambda **kw: [])
    monkeypatch.setattr(pipeline, "perform_market_and_competitor_research_for_consulting_case", lambda **kw: None)
    monkeypatch.setattr(pipeline, "extract_useful_business_information_for_consulting_case", lambda **kw: None)

    def fake_diagnose(consulting_case_id, company_name):
        return _make_diagnosis(consulting_case_id, recommend_marketing)

    monkeypatch.setattr(pipeline, "analyze_company_business_case_for_consulting_case", fake_diagnose)

    def fake_generate_report(consulting_case_id, company_name):
        diagnosis = _make_diagnosis(consulting_case_id, recommend_marketing)
        if recommend_marketing:
            strategy = MarketingStrategy(
                consulting_case_id=consulting_case_id,
                generated_because=StrategyGenerationReason.DIAGNOSIS_RECOMMENDED_MARKETING,
                executive_summary="A strategy.",
            )
            return GeneratedReport(
                consulting_case_id=consulting_case_id,
                report_type=ReportType.DIAGNOSIS_AND_STRATEGY,
                diagnosis=diagnosis,
                strategy=strategy,
            )
        return GeneratedReport(
            consulting_case_id=consulting_case_id,
            report_type=ReportType.DIAGNOSIS_ONLY,
            diagnosis=diagnosis,
        )

    monkeypatch.setattr(pipeline, "generate_business_diagnosis_report_for_consulting_case", fake_generate_report)

    def fake_create_pptx(consulting_case_id, company_name):
        return fake_generate_report(consulting_case_id, company_name).model_copy(
            update={"powerpoint_file_path": f"/tmp/{consulting_case_id}.pptx"}
        )

    monkeypatch.setattr(pipeline, "create_business_consulting_presentation_for_consulting_case", fake_create_pptx)


def test_pipeline_happy_path_marketing_needed_produces_strategy_report(isolated_test_database, monkeypatch):
    case_id_holder: dict = {}
    _patch_common_pipeline_steps(monkeypatch, case_id_holder, recommend_marketing=True)

    report = pipeline.run_consulting_case_analysis_pipeline(
        company_name="Acme Corp", website_url="https://acme.example.com"
    )

    assert report.report_type == ReportType.DIAGNOSIS_AND_STRATEGY
    assert report.powerpoint_file_path is not None

    final_case = get_consulting_case_by_id(report.consulting_case_id)
    assert final_case.status == ConsultingCaseStatus.COMPLETED


def test_pipeline_happy_path_no_marketing_needed_produces_diagnosis_only_report(
    isolated_test_database, monkeypatch
):
    case_id_holder: dict = {}
    _patch_common_pipeline_steps(monkeypatch, case_id_holder, recommend_marketing=False)

    report = pipeline.run_consulting_case_analysis_pipeline(
        company_name="Acme Corp", website_url="https://acme.example.com"
    )

    assert report.report_type == ReportType.DIAGNOSIS_ONLY
    assert report.strategy is None

    final_case = get_consulting_case_by_id(report.consulting_case_id)
    assert final_case.status == ConsultingCaseStatus.COMPLETED


def test_pipeline_raises_and_marks_case_failed_when_no_input_sources(isolated_test_database):
    with pytest.raises(ConsultingPipelineError, match="no input source"):
        pipeline.run_consulting_case_analysis_pipeline(company_name="Ghost Co")

    from storage.consulting_case_repository import list_all_consulting_cases

    cases = [c for c in list_all_consulting_cases() if c.company_name == "Ghost Co"]
    assert len(cases) == 1
    assert cases[0].status == ConsultingCaseStatus.FAILED
    assert "no input source" in cases[0].failure_reason


def test_pipeline_marks_case_failed_when_diagnosis_raises(isolated_test_database, monkeypatch):
    case_id_holder: dict = {}
    _patch_common_pipeline_steps(monkeypatch, case_id_holder, recommend_marketing=True)

    def fake_failing_diagnosis(consulting_case_id, company_name):
        raise OrchestratorError("Could not generate a business diagnosis: LLM unavailable")

    monkeypatch.setattr(pipeline, "analyze_company_business_case_for_consulting_case", fake_failing_diagnosis)

    with pytest.raises(OrchestratorError, match="LLM unavailable"):
        pipeline.run_consulting_case_analysis_pipeline(
            company_name="Acme Corp", website_url="https://acme.example.com"
        )

    failed_case = get_consulting_case_by_id(case_id_holder["id"])
    assert failed_case.status == ConsultingCaseStatus.FAILED
    assert "LLM unavailable" in failed_case.failure_reason


def test_pipeline_records_expected_status_transitions_for_marketing_needed_path(
    isolated_test_database, monkeypatch
):
    case_id_holder: dict = {}
    _patch_common_pipeline_steps(monkeypatch, case_id_holder, recommend_marketing=True)

    recorded_statuses: list[ConsultingCaseStatus] = []
    from storage import update_consulting_case_status as real_update_status

    def spying_update_status(case_id, status, failure_reason=None):
        recorded_statuses.append(status)
        return real_update_status(case_id, status, failure_reason=failure_reason)

    monkeypatch.setattr(pipeline, "update_consulting_case_status", spying_update_status)

    pipeline.run_consulting_case_analysis_pipeline(company_name="Acme Corp", website_url="https://acme.example.com")

    assert recorded_statuses == [
        ConsultingCaseStatus.COLLECTING_INFORMATION,
        ConsultingCaseStatus.PERFORMING_MARKET_RESEARCH,
        ConsultingCaseStatus.EXTRACTING_INFORMATION,
        ConsultingCaseStatus.DIAGNOSING_BUSINESS_CASE,
        ConsultingCaseStatus.GENERATING_STRATEGY,
        ConsultingCaseStatus.COMPLETED,
    ]


def test_pipeline_skips_generating_strategy_status_when_marketing_not_needed(
    isolated_test_database, monkeypatch
):
    case_id_holder: dict = {}
    _patch_common_pipeline_steps(monkeypatch, case_id_holder, recommend_marketing=False)

    recorded_statuses: list[ConsultingCaseStatus] = []
    from storage import update_consulting_case_status as real_update_status

    def spying_update_status(case_id, status, failure_reason=None):
        recorded_statuses.append(status)
        return real_update_status(case_id, status, failure_reason=failure_reason)

    monkeypatch.setattr(pipeline, "update_consulting_case_status", spying_update_status)

    pipeline.run_consulting_case_analysis_pipeline(company_name="Acme Corp", website_url="https://acme.example.com")

    assert ConsultingCaseStatus.GENERATING_STRATEGY not in recorded_statuses
    assert recorded_statuses[-1] == ConsultingCaseStatus.COMPLETED


def test_collect_company_information_from_all_sources_only_calls_relevant_collectors(monkeypatch):
    from domain import ConsultingCase

    called = {"website": 0, "pdf": 0, "social": 0}

    monkeypatch.setattr(
        pipeline, "collect_website_content_for_consulting_case",
        lambda **kw: called.__setitem__("website", called["website"] + 1) or [],
    )
    monkeypatch.setattr(
        pipeline, "collect_pdf_content_for_consulting_case",
        lambda **kw: called.__setitem__("pdf", called["pdf"] + 1),
    )
    monkeypatch.setattr(
        pipeline, "collect_social_media_profiles_for_consulting_case",
        lambda **kw: called.__setitem__("social", called["social"] + 1) or [],
    )

    case = ConsultingCase(id="case-1", company_name="Acme Corp", website_url="https://acme.example.com")
    pipeline.collect_company_information_from_all_sources(case)

    assert called == {"website": 1, "pdf": 0, "social": 1}  # social always attempted; internally no-ops if no urls


def test_collect_company_information_from_all_sources_treats_additional_links_as_single_pages(monkeypatch):
    from domain import ConsultingCase

    captured_calls = []

    def fake_collect_website(consulting_case_id, website_url, max_pages=None):
        captured_calls.append((website_url, max_pages))
        return []

    monkeypatch.setattr(pipeline, "collect_website_content_for_consulting_case", fake_collect_website)
    monkeypatch.setattr(pipeline, "collect_social_media_profiles_for_consulting_case", lambda **kw: [])

    case = ConsultingCase(
        id="case-1",
        company_name="Acme Corp",
        additional_links=["https://acme.example.com/blog/post-1"],
    )
    pipeline.collect_company_information_from_all_sources(case)

    assert len(captured_calls) == 1
    url, max_pages = captured_calls[0]
    assert "post-1" in str(url)
    assert max_pages == 1


def test_generate_marketing_strategy_report_for_existing_case_success(isolated_test_database, monkeypatch):
    from storage.consulting_case_repository import create_consulting_case as real_create_case

    real_case = real_create_case(company_name="Acme Corp")

    diagnosis = _make_diagnosis(real_case.id, recommend_marketing=False)
    strategy = MarketingStrategy(
        consulting_case_id=real_case.id,
        generated_because=StrategyGenerationReason.USER_REQUESTED_STRATEGY_DESPITE_DIAGNOSIS,
        executive_summary="Override strategy.",
        override_warning_message="The diagnosis indicates marketing is not the primary issue...",
    )
    override_report = GeneratedReport(
        consulting_case_id=real_case.id, report_type=ReportType.DIAGNOSIS_AND_STRATEGY,
        diagnosis=diagnosis, strategy=strategy,
    )

    monkeypatch.setattr(
        pipeline, "generate_marketing_strategy_report_despite_diagnosis_for_consulting_case",
        lambda consulting_case_id, company_name: override_report,
    )
    monkeypatch.setattr(
        pipeline, "create_business_consulting_presentation_for_consulting_case",
        lambda consulting_case_id, company_name: override_report.model_copy(
            update={"powerpoint_file_path": "/tmp/override.pptx"}
        ),
    )

    result = pipeline.generate_marketing_strategy_report_for_existing_case(real_case.id, "Acme Corp")

    assert result.strategy.override_warning_message is not None
    assert result.powerpoint_file_path == "/tmp/override.pptx"

    final_case = get_consulting_case_by_id(real_case.id)
    assert final_case.status == ConsultingCaseStatus.COMPLETED


def test_generate_marketing_strategy_report_for_existing_case_marks_failed_on_error(
    isolated_test_database, monkeypatch
):
    from storage.consulting_case_repository import create_consulting_case as real_create_case

    real_case = real_create_case(company_name="Acme Corp")

    def fake_failing_override(consulting_case_id, company_name):
        raise OrchestratorError("already recommended marketing")

    monkeypatch.setattr(
        pipeline, "generate_marketing_strategy_report_despite_diagnosis_for_consulting_case", fake_failing_override
    )

    with pytest.raises(OrchestratorError, match="already recommended marketing"):
        pipeline.generate_marketing_strategy_report_for_existing_case(real_case.id, "Acme Corp")

    failed_case = get_consulting_case_by_id(real_case.id)
    assert failed_case.status == ConsultingCaseStatus.FAILED
    assert "already recommended marketing" in failed_case.failure_reason
