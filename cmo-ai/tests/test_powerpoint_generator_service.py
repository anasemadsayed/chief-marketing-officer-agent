"""
Tests for the PowerPoint Generator Service (Brick 10).

No mocking of python-pptx itself — these tests generate real .pptx files
to a temp directory and re-open them with python-pptx to verify actual
structure and content. Visual/layout quality was separately verified by
hand using the pptx skill's QA tooling (validate.py + LibreOffice
render) during development; see the chat for those results.

Covers both report types: DIAGNOSIS_ONLY and DIAGNOSIS_AND_STRATEGY
(including the override-disclaimer slide and initiative pagination).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pptx import Presentation

from domain import (
    BusinessDiagnosis,
    ConfidenceLevel,
    Finding,
    GeneratedReport,
    MarketingNecessityDecision,
    MarketingStrategy,
    ReportType,
    StrategyGenerationReason,
    StrategyInitiative,
)
from services.powerpoint_generator_service import (
    PowerPointGenerationError,
    _chunk_list,
    create_business_consulting_presentation,
    create_business_consulting_presentation_for_consulting_case,
)
from storage.business_diagnosis_repository import save_business_diagnosis
from storage.consulting_case_repository import create_consulting_case
from storage.generated_report_repository import get_generated_report_by_case_id, save_generated_report


def _make_diagnosis(
    decision=MarketingNecessityDecision.MARKETING_IS_THE_PRIMARY_ISSUE, case_id="case-1"
) -> BusinessDiagnosis:
    return BusinessDiagnosis(
        consulting_case_id=case_id,
        decision=decision,
        primary_bottleneck="Low brand awareness in an otherwise well-served segment.",
        reasoning_summary="Product and pricing are competitive; awareness is the gap.",
        confidence=ConfidenceLevel.MEDIUM,
        supporting_findings=[
            Finding(
                description="No blog or content marketing presence found",
                evidence="No blog page discoverable on the website",
                confidence=ConfidenceLevel.MEDIUM,
            ),
        ],
    )


def test_chunk_list_splits_into_even_groups():
    assert _chunk_list([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_chunk_list_returns_empty_list_for_empty_input():
    assert _chunk_list([], 4) == []


def test_create_presentation_diagnosis_only_produces_valid_pptx(tmp_path):
    diagnosis = _make_diagnosis(decision=MarketingNecessityDecision.MARKETING_IS_NOT_THE_PRIMARY_ISSUE)
    report = GeneratedReport(
        consulting_case_id="case-1", report_type=ReportType.DIAGNOSIS_ONLY, diagnosis=diagnosis
    )
    output_path = tmp_path / "report.pptx"

    result_path = create_business_consulting_presentation(report, "Acme Corp", str(output_path))

    assert Path(result_path).exists()
    presentation = Presentation(result_path)
    all_text = _extract_all_text(presentation)

    assert "Acme Corp" in all_text
    assert "MARKETING IS NOT THE PRIMARY ISSUE" in all_text
    assert "No blog or content marketing presence found" in all_text
    assert "Confidence: MEDIUM" in all_text
    assert "Thank you" in all_text
    # Title + Diagnosis + 1 findings slide + Closing = 4 slides.
    assert len(presentation.slides) == 4


def test_create_presentation_paginates_many_findings(tmp_path):
    findings = [
        Finding(description=f"Finding {i}", evidence=f"Evidence {i}", confidence=ConfidenceLevel.MEDIUM)
        for i in range(9)
    ]
    diagnosis = _make_diagnosis()
    diagnosis = diagnosis.model_copy(update={"supporting_findings": findings})
    report = GeneratedReport(consulting_case_id="case-1", report_type=ReportType.DIAGNOSIS_ONLY, diagnosis=diagnosis)
    output_path = tmp_path / "report.pptx"

    create_business_consulting_presentation(report, "Acme Corp", str(output_path))

    presentation = Presentation(output_path)
    all_text = _extract_all_text(presentation)
    for i in range(9):
        assert f"Finding {i}" in all_text
    # 9 findings at 4 per slide -> 3 findings slides, plus title + diagnosis + closing = 6 slides.
    assert len(presentation.slides) == 6


def test_create_presentation_diagnosis_and_strategy_renders_all_strategy_slides(tmp_path):
    diagnosis = _make_diagnosis()
    strategy = MarketingStrategy(
        consulting_case_id="case-1",
        generated_because=StrategyGenerationReason.DIAGNOSIS_RECOMMENDED_MARKETING,
        executive_summary="Build category awareness via content and targeted outbound in Q1.",
        strategic_objectives=["Increase inbound demo requests by 30%"],
        recommended_channels=["LinkedIn outbound", "SEO content"],
        key_initiatives=[
            StrategyInitiative(
                title="Launch LinkedIn outbound",
                description="Target VP-level buyers at mid-market SaaS companies.",
                expected_impact="Directly reaches the identified target audience.",
            ),
        ],
    )
    report = GeneratedReport(
        consulting_case_id="case-1", report_type=ReportType.DIAGNOSIS_AND_STRATEGY,
        diagnosis=diagnosis, strategy=strategy,
    )
    output_path = tmp_path / "report.pptx"

    result_path = create_business_consulting_presentation(report, "Acme Corp", str(output_path))

    presentation = Presentation(result_path)
    all_text = _extract_all_text(presentation)

    assert "Build category awareness" in all_text
    assert "Increase inbound demo requests by 30%" in all_text
    assert "LinkedIn outbound" in all_text
    assert "Launch LinkedIn outbound" in all_text
    assert "Directly reaches the identified target audience." in all_text
    assert "Requested Despite Diagnosis" not in all_text  # no override -> no notice slide
    # Title + Diagnosis + 1 findings + ExecSummary + Objectives/Channels + 1 initiatives + Closing = 7.
    assert len(presentation.slides) == 7


def test_create_presentation_renders_override_notice_slide_when_present(tmp_path):
    diagnosis = _make_diagnosis(decision=MarketingNecessityDecision.MARKETING_IS_NOT_THE_PRIMARY_ISSUE)
    strategy = MarketingStrategy(
        consulting_case_id="case-1",
        generated_because=StrategyGenerationReason.USER_REQUESTED_STRATEGY_DESPITE_DIAGNOSIS,
        executive_summary="Strategy generated on user request despite the diagnosis.",
        override_warning_message=(
            "The diagnosis indicates that marketing is not the primary business "
            "issue and this strategy is generated only because the user "
            "explicitly requested it."
        ),
    )
    report = GeneratedReport(
        consulting_case_id="case-1", report_type=ReportType.DIAGNOSIS_AND_STRATEGY,
        diagnosis=diagnosis, strategy=strategy,
    )
    output_path = tmp_path / "report.pptx"

    create_business_consulting_presentation(report, "Acme Corp", str(output_path))

    presentation = Presentation(output_path)
    all_text = _extract_all_text(presentation)

    assert "Requested Despite Diagnosis" in all_text
    assert "explicitly requested it" in all_text
    # Title + Diagnosis + 1 findings + Override notice + ExecSummary + Objectives/Channels + Closing = 7.
    assert len(presentation.slides) == 7


def test_create_presentation_paginates_many_key_initiatives(tmp_path):
    diagnosis = _make_diagnosis()
    initiatives = [
        StrategyInitiative(title=f"Initiative {i}", description=f"Description {i}")
        for i in range(6)
    ]
    strategy = MarketingStrategy(
        consulting_case_id="case-1",
        generated_because=StrategyGenerationReason.DIAGNOSIS_RECOMMENDED_MARKETING,
        executive_summary="Six-initiative strategy to test pagination.",
        key_initiatives=initiatives,
    )
    report = GeneratedReport(
        consulting_case_id="case-1", report_type=ReportType.DIAGNOSIS_AND_STRATEGY,
        diagnosis=diagnosis, strategy=strategy,
    )
    output_path = tmp_path / "report.pptx"

    create_business_consulting_presentation(report, "Acme Corp", str(output_path))

    presentation = Presentation(output_path)
    all_text = _extract_all_text(presentation)
    for i in range(6):
        assert f"Initiative {i}" in all_text
    # 6 initiatives at 4 per slide -> 2 initiative slides.
    # Title + Diagnosis + 1 findings + ExecSummary + Objectives/Channels + 2 initiative slides + Closing = 8.
    assert len(presentation.slides) == 8


def test_create_presentation_renders_strategy_supporting_findings(tmp_path):
    diagnosis = _make_diagnosis()
    strategy = MarketingStrategy(
        consulting_case_id="case-1",
        generated_because=StrategyGenerationReason.DIAGNOSIS_RECOMMENDED_MARKETING,
        executive_summary="Strategy with its own supporting evidence.",
        supporting_findings=[
            Finding(
                description="No existing content marketing presence",
                evidence="No blog page found in collected sources",
                confidence=ConfidenceLevel.MEDIUM,
            ),
        ],
    )
    report = GeneratedReport(
        consulting_case_id="case-1", report_type=ReportType.DIAGNOSIS_AND_STRATEGY,
        diagnosis=diagnosis, strategy=strategy,
    )
    output_path = tmp_path / "report.pptx"

    create_business_consulting_presentation(report, "Acme Corp", str(output_path))

    presentation = Presentation(output_path)
    all_text = _extract_all_text(presentation)
    assert "Strategy Evidence" in all_text
    assert "No existing content marketing presence" in all_text


def test_create_presentation_raises_powerpoint_error_on_bad_path():
    diagnosis = _make_diagnosis()
    report = GeneratedReport(consulting_case_id="case-1", report_type=ReportType.DIAGNOSIS_ONLY, diagnosis=diagnosis)

    with pytest.raises(PowerPointGenerationError):
        create_business_consulting_presentation(report, "Acme Corp", "/this/path/does/not/exist/\x00bad.pptx")


def test_for_consulting_case_raises_when_no_report_exists(isolated_test_database):
    case = create_consulting_case(company_name="Acme Corp")

    with pytest.raises(PowerPointGenerationError, match="no generated report found"):
        create_business_consulting_presentation_for_consulting_case(case.id, "Acme Corp", output_directory="/tmp")


def test_for_consulting_case_saves_path_and_updates_report(isolated_test_database, tmp_path):
    case = create_consulting_case(company_name="Acme Corp")
    diagnosis = _make_diagnosis(case_id=case.id)
    save_business_diagnosis(diagnosis)
    save_generated_report(
        GeneratedReport(consulting_case_id=case.id, report_type=ReportType.DIAGNOSIS_ONLY, diagnosis=diagnosis)
    )

    updated_report = create_business_consulting_presentation_for_consulting_case(
        case.id, "Acme Corp", output_directory=str(tmp_path)
    )

    assert updated_report.powerpoint_file_path is not None
    assert Path(updated_report.powerpoint_file_path).exists()

    persisted = get_generated_report_by_case_id(case.id)
    assert persisted.powerpoint_file_path == updated_report.powerpoint_file_path


def test_for_consulting_case_degrades_gracefully_when_rendering_fails(isolated_test_database, monkeypatch):
    case = create_consulting_case(company_name="Acme Corp")
    diagnosis = _make_diagnosis(case_id=case.id)
    save_business_diagnosis(diagnosis)
    save_generated_report(
        GeneratedReport(consulting_case_id=case.id, report_type=ReportType.DIAGNOSIS_ONLY, diagnosis=diagnosis)
    )

    import services.powerpoint_generator_service as service_module

    def fake_failing_render(report, company_name, output_path):
        raise PowerPointGenerationError("simulated rendering failure")

    monkeypatch.setattr(service_module, "create_business_consulting_presentation", fake_failing_render)

    result = create_business_consulting_presentation_for_consulting_case(
        case.id, "Acme Corp", output_directory="/tmp"
    )

    # Never raises; the report is still valid, just without a deck.
    assert result.powerpoint_file_path is None
    assert result.diagnosis.primary_bottleneck == diagnosis.primary_bottleneck


def test_diagnosis_only_end_to_end_via_storage(isolated_test_database, tmp_path):
    """Full realistic round trip: save everything, generate the deck, verify it opens."""
    case = create_consulting_case(company_name="Acme Corp")
    diagnosis = _make_diagnosis(
        decision=MarketingNecessityDecision.MARKETING_IS_NOT_THE_PRIMARY_ISSUE, case_id=case.id
    )
    save_business_diagnosis(diagnosis)
    save_generated_report(
        GeneratedReport(consulting_case_id=case.id, report_type=ReportType.DIAGNOSIS_ONLY, diagnosis=diagnosis)
    )

    updated_report = create_business_consulting_presentation_for_consulting_case(
        case.id, "Acme Corp", output_directory=str(tmp_path)
    )

    presentation = Presentation(updated_report.powerpoint_file_path)
    assert len(presentation.slides) == 4


def _extract_all_text(presentation: Presentation) -> str:
    """Concatenate every run of text across every slide, for simple substring assertions."""
    chunks: list[str] = []
    for slide in presentation.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                for paragraph in shape.text_frame.paragraphs:
                    for run in paragraph.runs:
                        chunks.append(run.text)
    return "\n".join(chunks)
