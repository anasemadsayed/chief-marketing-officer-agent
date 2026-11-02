"""
Tests for the orchestrator's marketing strategy generator (Brick 9, Part 1).

The main LLM call is monkeypatched at the
`generate_json_response_from_main_llm` boundary so these tests never hit
a real API. Two things matter most here:
1. A strategy generated via the override path always carries the
   required disclaimer, worded consistently (hardcoded, not LLM-authored).
2. Calling with DIAGNOSIS_RECOMMENDED_MARKETING against a "no" diagnosis
   is blocked — this is the structural enforcement of "never force a
   marketing strategy if marketing isn't the real problem."
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
    StrategyGenerationReason,
)
from orchestrator import marketing_strategy_generator as generator
from orchestrator.errors import OrchestratorError
from orchestrator.main_llm_client import MainLlmClientError
from storage.business_diagnosis_repository import save_business_diagnosis
from storage.consulting_case_repository import create_consulting_case
from storage.extracted_company_information_repository import save_extracted_information
from storage.market_research_repository import save_market_research
from storage.marketing_strategy_repository import get_marketing_strategy_by_case_id

VALID_STRATEGY_RESPONSE = {
    "executive_summary": "Build category awareness via content and targeted outbound in Q1.",
    "strategic_objectives": ["Increase inbound demo requests by 30%"],
    "recommended_channels": ["LinkedIn outbound", "SEO content"],
    "key_initiatives": [
        {
            "title": "Launch LinkedIn outbound",
            "description": "Target VP-level buyers at mid-market SaaS companies.",
            "expected_impact": "Directly reaches the identified target audience.",
            "supporting_evidence": ["Target audience signals: mid-market SaaS buyers"],
        },
        {
            "title": "Publish comparison content",
            "description": "Write content comparing pricing/features against named competitors.",
            "expected_impact": "Addresses the competitive positioning gap found in research.",
            "supporting_evidence": ["Competitor Rival Inc charges $35/user/month"],
        },
    ],
    "supporting_findings": [
        {
            "description": "No existing content marketing presence",
            "evidence": "No blog page found in collected sources",
            "source_reference": "extracted_information:notable_content_snippets",
            "confidence": "medium",
        }
    ],
}


def _make_diagnosis(decision=MarketingNecessityDecision.MARKETING_IS_THE_PRIMARY_ISSUE, case_id="case-1") -> BusinessDiagnosis:
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
        target_audience_signals=["Mid-market SaaS buyers"],
    )


def _make_market_research(case_id="case-1") -> MarketResearch:
    return MarketResearch(
        consulting_case_id=case_id,
        industry_overview="B2B SaaS project management",
        competitors=[CompetitorProfile(name="Rival Inc", notes="$35/user/month")],
    )


def test_generate_marketing_strategy_saves_successful_result(isolated_test_database, monkeypatch):
    case = create_consulting_case(company_name="Acme Corp")

    monkeypatch.setattr(
        generator, "generate_json_response_from_main_llm",
        lambda prompt, temperature, max_output_tokens: VALID_STRATEGY_RESPONSE,
    )

    result = generator.generate_marketing_strategy(
        consulting_case_id=case.id,
        company_name="Acme Corp",
        diagnosis=_make_diagnosis(case_id=case.id),
        extracted_information=_make_extracted_information(case.id),
        market_research=_make_market_research(case.id),
    )

    assert result.generated_because == StrategyGenerationReason.DIAGNOSIS_RECOMMENDED_MARKETING
    assert result.override_warning_message is None
    assert len(result.key_initiatives) == 2
    assert result.key_initiatives[0].title == "Launch LinkedIn outbound"

    persisted = get_marketing_strategy_by_case_id(case.id)
    assert persisted is not None


def test_generate_marketing_strategy_blocks_recommended_reason_against_no_diagnosis(
    isolated_test_database,
):
    case = create_consulting_case(company_name="Acme Corp")
    no_diagnosis = _make_diagnosis(
        decision=MarketingNecessityDecision.MARKETING_IS_NOT_THE_PRIMARY_ISSUE, case_id=case.id
    )

    with pytest.raises(OrchestratorError, match="did not recommend marketing"):
        generator.generate_marketing_strategy(
            consulting_case_id=case.id,
            company_name="Acme Corp",
            diagnosis=no_diagnosis,
            extracted_information=_make_extracted_information(case.id),
            market_research=_make_market_research(case.id),
            generated_because=StrategyGenerationReason.DIAGNOSIS_RECOMMENDED_MARKETING,
        )

    assert get_marketing_strategy_by_case_id(case.id) is None


def test_generate_marketing_strategy_blocks_override_reason_against_yes_diagnosis(
    isolated_test_database,
):
    case = create_consulting_case(company_name="Acme Corp")
    yes_diagnosis = _make_diagnosis(
        decision=MarketingNecessityDecision.MARKETING_IS_THE_PRIMARY_ISSUE, case_id=case.id
    )

    with pytest.raises(OrchestratorError, match="already recommended marketing"):
        generator.generate_marketing_strategy(
            consulting_case_id=case.id,
            company_name="Acme Corp",
            diagnosis=yes_diagnosis,
            extracted_information=_make_extracted_information(case.id),
            market_research=_make_market_research(case.id),
            generated_because=StrategyGenerationReason.USER_REQUESTED_STRATEGY_DESPITE_DIAGNOSIS,
        )

    assert get_marketing_strategy_by_case_id(case.id) is None


def test_generate_marketing_strategy_override_path_attaches_required_disclaimer(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")
    no_diagnosis = _make_diagnosis(
        decision=MarketingNecessityDecision.MARKETING_IS_NOT_THE_PRIMARY_ISSUE, case_id=case.id
    )

    monkeypatch.setattr(
        generator, "generate_json_response_from_main_llm",
        lambda prompt, temperature, max_output_tokens: VALID_STRATEGY_RESPONSE,
    )

    result = generator.generate_marketing_strategy(
        consulting_case_id=case.id,
        company_name="Acme Corp",
        diagnosis=no_diagnosis,
        extracted_information=_make_extracted_information(case.id),
        market_research=_make_market_research(case.id),
        generated_because=StrategyGenerationReason.USER_REQUESTED_STRATEGY_DESPITE_DIAGNOSIS,
    )

    assert result.generated_because == StrategyGenerationReason.USER_REQUESTED_STRATEGY_DESPITE_DIAGNOSIS
    assert result.override_warning_message is not None
    assert "marketing is not the primary business issue" in result.override_warning_message
    assert "explicitly requested it" in result.override_warning_message
    assert no_diagnosis.primary_bottleneck in result.override_warning_message


def test_generate_marketing_strategy_raises_and_saves_nothing_on_llm_failure(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")

    def fake_failing_call(prompt, temperature, max_output_tokens):
        raise MainLlmClientError("No Gemini API key configured.")

    monkeypatch.setattr(generator, "generate_json_response_from_main_llm", fake_failing_call)

    with pytest.raises(OrchestratorError, match="Could not generate a marketing strategy"):
        generator.generate_marketing_strategy(
            consulting_case_id=case.id,
            company_name="Acme Corp",
            diagnosis=_make_diagnosis(case_id=case.id),
            extracted_information=_make_extracted_information(case.id),
            market_research=_make_market_research(case.id),
        )

    assert get_marketing_strategy_by_case_id(case.id) is None


def test_generate_marketing_strategy_raises_and_saves_nothing_on_malformed_response(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")

    malformed = {"executive_summary": "ok", "key_initiatives": "not a list"}
    monkeypatch.setattr(
        generator, "generate_json_response_from_main_llm",
        lambda prompt, temperature, max_output_tokens: malformed,
    )

    with pytest.raises(OrchestratorError):
        generator.generate_marketing_strategy(
            consulting_case_id=case.id,
            company_name="Acme Corp",
            diagnosis=_make_diagnosis(case_id=case.id),
            extracted_information=_make_extracted_information(case.id),
            market_research=_make_market_research(case.id),
        )

    assert get_marketing_strategy_by_case_id(case.id) is None


def test_generate_marketing_strategy_raises_when_executive_summary_empty(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")
    empty_summary_response = {**VALID_STRATEGY_RESPONSE, "executive_summary": ""}

    monkeypatch.setattr(
        generator, "generate_json_response_from_main_llm",
        lambda prompt, temperature, max_output_tokens: empty_summary_response,
    )

    with pytest.raises(OrchestratorError):
        generator.generate_marketing_strategy(
            consulting_case_id=case.id,
            company_name="Acme Corp",
            diagnosis=_make_diagnosis(case_id=case.id),
            extracted_information=_make_extracted_information(case.id),
            market_research=_make_market_research(case.id),
        )

    assert get_marketing_strategy_by_case_id(case.id) is None


def test_generate_marketing_strategy_for_consulting_case_raises_when_diagnosis_missing(
    isolated_test_database,
):
    case = create_consulting_case(company_name="Acme Corp")

    with pytest.raises(OrchestratorError, match="no diagnosis"):
        generator.generate_marketing_strategy_for_consulting_case(case.id, "Acme Corp")


def test_generate_marketing_strategy_for_consulting_case_raises_when_extraction_missing(
    isolated_test_database,
):
    case = create_consulting_case(company_name="Acme Corp")
    save_business_diagnosis(_make_diagnosis(case_id=case.id))

    with pytest.raises(OrchestratorError, match="no extracted"):
        generator.generate_marketing_strategy_for_consulting_case(case.id, "Acme Corp")


def test_generate_marketing_strategy_for_consulting_case_raises_when_market_research_missing(
    isolated_test_database,
):
    case = create_consulting_case(company_name="Acme Corp")
    save_business_diagnosis(_make_diagnosis(case_id=case.id))
    save_extracted_information(_make_extracted_information(case.id))

    with pytest.raises(OrchestratorError, match="no market"):
        generator.generate_marketing_strategy_for_consulting_case(case.id, "Acme Corp")


def test_generate_marketing_strategy_for_consulting_case_pulls_from_storage(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")
    save_business_diagnosis(_make_diagnosis(case_id=case.id))
    save_extracted_information(_make_extracted_information(case.id))
    save_market_research(_make_market_research(case.id))

    captured_prompts = []

    def fake_call(prompt, temperature, max_output_tokens):
        captured_prompts.append(prompt)
        return VALID_STRATEGY_RESPONSE

    monkeypatch.setattr(generator, "generate_json_response_from_main_llm", fake_call)

    result = generator.generate_marketing_strategy_for_consulting_case(case.id, "Acme Corp")

    assert result.executive_summary == VALID_STRATEGY_RESPONSE["executive_summary"]
    assert "Acme builds project management software" in captured_prompts[0]
    assert "Rival Inc" in captured_prompts[0]
