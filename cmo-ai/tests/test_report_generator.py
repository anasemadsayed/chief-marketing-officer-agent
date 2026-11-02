"""
Tests for the orchestrator's report generation and decision wiring
(Brick 9, Part 2).

This is the most business-critical test file in the project: it proves
the central product promise actually holds in code —
1. "Yes" diagnosis -> strategy auto-generated, DIAGNOSIS_AND_STRATEGY report.
2. "No" diagnosis -> NO strategy generated automatically, DIAGNOSIS_ONLY report.
3. Explicit override -> strategy generated with the required disclaimer,
   even though the diagnosis said no.
4. Any failure along the way -> nothing fabricated, nothing saved.
"""

from __future__ import annotations

import pytest

from domain import (
    BusinessDiagnosis,
    CompetitorProfile,
    ConfidenceLevel,
    ExtractedCompanyInformation,
    MarketResearch,
    MarketingNecessityDecision,
    ReportType,
)
from orchestrator import marketing_strategy_generator
from orchestrator import report_generator as generator
from orchestrator.errors import OrchestratorError
from storage.business_diagnosis_repository import save_business_diagnosis
from storage.consulting_case_repository import create_consulting_case
from storage.extracted_company_information_repository import save_extracted_information
from storage.generated_report_repository import get_generated_report_by_case_id
from storage.market_research_repository import save_market_research

VALID_STRATEGY_RESPONSE = {
    "executive_summary": "Build category awareness via content and targeted outbound in Q1.",
    "strategic_objectives": ["Increase inbound demo requests by 30%"],
    "recommended_channels": ["LinkedIn outbound", "SEO content"],
    "key_initiatives": [
        {
            "title": "Launch LinkedIn outbound",
            "description": "Target VP-level buyers at mid-market SaaS companies.",
            "expected_impact": "Directly reaches the identified target audience.",
        }
    ],
    "supporting_findings": [],
}


def _make_diagnosis(
    decision=MarketingNecessityDecision.MARKETING_IS_THE_PRIMARY_ISSUE, case_id="case-1"
) -> BusinessDiagnosis:
    return BusinessDiagnosis(
        consulting_case_id=case_id,
        decision=decision,
        primary_bottleneck="Low brand awareness in an otherwise well-served segment.",
        reasoning_summary="Product and pricing are competitive; awareness is the gap.",
        confidence=ConfidenceLevel.MEDIUM,
    )


def _make_extracted_information(case_id="case-1") -> ExtractedCompanyInformation:
    return ExtractedCompanyInformation(
        consulting_case_id=case_id,
        company_description_summary="Acme builds project management software.",
    )


def _make_market_research(case_id="case-1") -> MarketResearch:
    return MarketResearch(
        consulting_case_id=case_id,
        industry_overview="B2B SaaS project management",
        competitors=[CompetitorProfile(name="Rival Inc")],
    )


# --- generate_business_diagnosis_report: the automatic yes/no branch -------


def test_yes_diagnosis_auto_generates_strategy_and_saves_combined_report(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")
    diagnosis = _make_diagnosis(case_id=case.id)

    monkeypatch.setattr(
        marketing_strategy_generator, "generate_json_response_from_main_llm",
        lambda prompt, temperature, max_output_tokens: VALID_STRATEGY_RESPONSE,
    )

    report = generator.generate_business_diagnosis_report(
        consulting_case_id=case.id,
        company_name="Acme Corp",
        diagnosis=diagnosis,
        extracted_information=_make_extracted_information(case.id),
        market_research=_make_market_research(case.id),
    )

    assert report.report_type == ReportType.DIAGNOSIS_AND_STRATEGY
    assert report.strategy is not None
    assert report.strategy.override_warning_message is None

    persisted = get_generated_report_by_case_id(case.id)
    assert persisted is not None
    assert persisted.report_type == ReportType.DIAGNOSIS_AND_STRATEGY


def test_no_diagnosis_never_calls_strategy_generation_and_saves_diagnosis_only_report(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")
    diagnosis = _make_diagnosis(
        decision=MarketingNecessityDecision.MARKETING_IS_NOT_THE_PRIMARY_ISSUE, case_id=case.id
    )

    llm_was_called = False

    def fake_call(prompt, temperature, max_output_tokens):
        nonlocal llm_was_called
        llm_was_called = True
        return VALID_STRATEGY_RESPONSE

    monkeypatch.setattr(marketing_strategy_generator, "generate_json_response_from_main_llm", fake_call)

    report = generator.generate_business_diagnosis_report(
        consulting_case_id=case.id,
        company_name="Acme Corp",
        diagnosis=diagnosis,
    )

    assert llm_was_called is False, "no strategy should ever be auto-generated for a 'no' diagnosis"
    assert report.report_type == ReportType.DIAGNOSIS_ONLY
    assert report.strategy is None

    persisted = get_generated_report_by_case_id(case.id)
    assert persisted is not None
    assert persisted.strategy is None


def test_yes_diagnosis_without_required_data_raises_and_saves_nothing(isolated_test_database):
    case = create_consulting_case(company_name="Acme Corp")
    diagnosis = _make_diagnosis(case_id=case.id)

    with pytest.raises(OrchestratorError, match="were not provided"):
        generator.generate_business_diagnosis_report(
            consulting_case_id=case.id,
            company_name="Acme Corp",
            diagnosis=diagnosis,
            # extracted_information / market_research intentionally omitted
        )

    assert get_generated_report_by_case_id(case.id) is None


def test_yes_diagnosis_propagates_strategy_failure_and_saves_nothing(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")
    diagnosis = _make_diagnosis(case_id=case.id)

    from orchestrator.main_llm_client import MainLlmClientError

    def fake_failing_llm(prompt, temperature, max_output_tokens):
        raise MainLlmClientError("No Gemini API key configured.")

    monkeypatch.setattr(
        marketing_strategy_generator, "generate_json_response_from_main_llm", fake_failing_llm
    )

    with pytest.raises(OrchestratorError):
        generator.generate_business_diagnosis_report(
            consulting_case_id=case.id,
            company_name="Acme Corp",
            diagnosis=diagnosis,
            extracted_information=_make_extracted_information(case.id),
            market_research=_make_market_research(case.id),
        )

    assert get_generated_report_by_case_id(case.id) is None


# --- generate_business_diagnosis_report_for_consulting_case ----------------


def test_for_consulting_case_raises_when_diagnosis_missing(isolated_test_database):
    case = create_consulting_case(company_name="Acme Corp")

    with pytest.raises(OrchestratorError, match="no diagnosis"):
        generator.generate_business_diagnosis_report_for_consulting_case(case.id, "Acme Corp")


def test_for_consulting_case_no_diagnosis_path_does_not_require_extraction_or_research(
    isolated_test_database,
):
    case = create_consulting_case(company_name="Acme Corp")
    save_business_diagnosis(
        _make_diagnosis(decision=MarketingNecessityDecision.MARKETING_IS_NOT_THE_PRIMARY_ISSUE, case_id=case.id)
    )
    # Deliberately no extracted_information or market_research saved.

    report = generator.generate_business_diagnosis_report_for_consulting_case(case.id, "Acme Corp")

    assert report.report_type == ReportType.DIAGNOSIS_ONLY


def test_for_consulting_case_yes_diagnosis_path_raises_when_supporting_data_missing(
    isolated_test_database,
):
    case = create_consulting_case(company_name="Acme Corp")
    save_business_diagnosis(_make_diagnosis(case_id=case.id))
    # Deliberately no extracted_information or market_research saved.

    with pytest.raises(OrchestratorError, match="extracted company information and/or market research"):
        generator.generate_business_diagnosis_report_for_consulting_case(case.id, "Acme Corp")


def test_for_consulting_case_yes_diagnosis_path_pulls_everything_from_storage(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")
    save_business_diagnosis(_make_diagnosis(case_id=case.id))
    save_extracted_information(_make_extracted_information(case.id))
    save_market_research(_make_market_research(case.id))

    monkeypatch.setattr(
        marketing_strategy_generator, "generate_json_response_from_main_llm",
        lambda prompt, temperature, max_output_tokens: VALID_STRATEGY_RESPONSE,
    )

    report = generator.generate_business_diagnosis_report_for_consulting_case(case.id, "Acme Corp")

    assert report.report_type == ReportType.DIAGNOSIS_AND_STRATEGY
    assert report.strategy.executive_summary == VALID_STRATEGY_RESPONSE["executive_summary"]


# --- generate_marketing_strategy_report_despite_diagnosis (override) -------


def test_override_report_carries_disclaimer_and_saves_combined_report(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")
    no_diagnosis = _make_diagnosis(
        decision=MarketingNecessityDecision.MARKETING_IS_NOT_THE_PRIMARY_ISSUE, case_id=case.id
    )

    monkeypatch.setattr(
        marketing_strategy_generator, "generate_json_response_from_main_llm",
        lambda prompt, temperature, max_output_tokens: VALID_STRATEGY_RESPONSE,
    )

    report = generator.generate_marketing_strategy_report_despite_diagnosis(
        consulting_case_id=case.id,
        company_name="Acme Corp",
        diagnosis=no_diagnosis,
        extracted_information=_make_extracted_information(case.id),
        market_research=_make_market_research(case.id),
    )

    assert report.report_type == ReportType.DIAGNOSIS_AND_STRATEGY
    assert report.strategy.override_warning_message is not None
    assert "explicitly requested it" in report.strategy.override_warning_message

    persisted = get_generated_report_by_case_id(case.id)
    assert persisted.strategy.override_warning_message is not None


def test_override_report_raises_when_diagnosis_actually_recommended_marketing(
    isolated_test_database,
):
    case = create_consulting_case(company_name="Acme Corp")
    yes_diagnosis = _make_diagnosis(case_id=case.id)

    with pytest.raises(OrchestratorError, match="already recommended marketing"):
        generator.generate_marketing_strategy_report_despite_diagnosis(
            consulting_case_id=case.id,
            company_name="Acme Corp",
            diagnosis=yes_diagnosis,
            extracted_information=_make_extracted_information(case.id),
            market_research=_make_market_research(case.id),
        )

    assert get_generated_report_by_case_id(case.id) is None


def test_override_for_consulting_case_requires_all_three_pieces_of_data(isolated_test_database):
    case = create_consulting_case(company_name="Acme Corp")

    with pytest.raises(OrchestratorError, match="no diagnosis"):
        generator.generate_marketing_strategy_report_despite_diagnosis_for_consulting_case(
            case.id, "Acme Corp"
        )

    save_business_diagnosis(
        _make_diagnosis(decision=MarketingNecessityDecision.MARKETING_IS_NOT_THE_PRIMARY_ISSUE, case_id=case.id)
    )
    with pytest.raises(OrchestratorError, match="no extracted company"):
        generator.generate_marketing_strategy_report_despite_diagnosis_for_consulting_case(
            case.id, "Acme Corp"
        )

    save_extracted_information(_make_extracted_information(case.id))
    with pytest.raises(OrchestratorError, match="no market research"):
        generator.generate_marketing_strategy_report_despite_diagnosis_for_consulting_case(
            case.id, "Acme Corp"
        )


def test_override_for_consulting_case_pulls_everything_from_storage(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")
    save_business_diagnosis(
        _make_diagnosis(decision=MarketingNecessityDecision.MARKETING_IS_NOT_THE_PRIMARY_ISSUE, case_id=case.id)
    )
    save_extracted_information(_make_extracted_information(case.id))
    save_market_research(_make_market_research(case.id))

    monkeypatch.setattr(
        marketing_strategy_generator, "generate_json_response_from_main_llm",
        lambda prompt, temperature, max_output_tokens: VALID_STRATEGY_RESPONSE,
    )

    report = generator.generate_marketing_strategy_report_despite_diagnosis_for_consulting_case(
        case.id, "Acme Corp"
    )

    assert report.report_type == ReportType.DIAGNOSIS_AND_STRATEGY
    assert report.strategy.override_warning_message is not None
