"""
Tests for the orchestrator's business diagnosis generator (Brick 8).

The main LLM call is monkeypatched at the
`generate_json_response_from_main_llm` boundary so these tests never hit
a real API. The most important behavior tested here is that failures
raise OrchestratorError and save NOTHING — the orchestrator must never
fabricate a diagnosis.
"""

from __future__ import annotations

import pytest

from domain import CompetitorProfile, ExtractedCompanyInformation, MarketResearch
from orchestrator import business_diagnosis_generator as generator
from orchestrator.errors import OrchestratorError
from orchestrator.main_llm_client import MainLlmClientError
from storage.business_diagnosis_repository import get_business_diagnosis_by_case_id
from storage.consulting_case_repository import create_consulting_case
from storage.extracted_company_information_repository import save_extracted_information
from storage.market_research_repository import save_market_research

VALID_LLM_RESPONSE_MARKETING_NEEDED = {
    "decision": "marketing_is_the_primary_issue",
    "primary_bottleneck": "Low brand awareness in an otherwise well-served target segment.",
    "reasoning_summary": (
        "The product is competitively priced and well-differentiated, but the "
        "company has no visible content or outbound presence, and website "
        "traffic signals are minimal. Awareness, not product or pricing, is "
        "the gap."
    ),
    "confidence": "medium",
    "supporting_findings": [
        {
            "description": "No blog or content marketing found",
            "evidence": "No blog page was discoverable on the company website",
            "source_reference": "extracted_information:notable_content_snippets",
            "confidence": "medium",
        },
        {
            "description": "Pricing is competitive with named rivals",
            "evidence": "$29/user/month vs competitor's $35/user/month",
            "source_reference": "extracted_information:pricing_information",
            "confidence": "high",
        },
    ],
}

VALID_LLM_RESPONSE_NOT_MARKETING = {
    "decision": "marketing_is_not_the_primary_issue",
    "primary_bottleneck": "Checkout flow has a severe drop-off problem.",
    "reasoning_summary": (
        "Traffic and top-of-funnel awareness appear healthy based on collected "
        "signals, but no completed purchases are mentioned anywhere, and "
        "pricing is unclear on the site itself, suggesting a conversion problem."
    ),
    "confidence": "high",
    "supporting_findings": [
        {
            "description": "Pricing page exists but lacks a clear call to action",
            "evidence": "Pricing content found but no 'buy' or 'sign up' language captured",
            "source_reference": "extracted_information:pricing_information",
            "confidence": "medium",
        },
        {
            "description": "No mention of checkout or purchase flow anywhere in collected content",
            "evidence": "No purchase-related snippets in notable_content_snippets",
            "source_reference": "extracted_information:notable_content_snippets",
            "confidence": "high",
        },
    ],
}


def _make_extracted_information(case_id: str = "case-1") -> ExtractedCompanyInformation:
    return ExtractedCompanyInformation(
        consulting_case_id=case_id,
        company_description_summary="Acme builds project management software.",
        value_proposition="The only PM tool built for distributed teams.",
        products_and_services=["Project tracker"],
        pricing_information=["$29/user/month"],
    )


def _make_market_research(case_id: str = "case-1") -> MarketResearch:
    return MarketResearch(
        consulting_case_id=case_id,
        industry_overview="B2B SaaS project management",
        competitors=[CompetitorProfile(name="Rival Inc", notes="$35/user/month")],
        market_trends=["AI-assisted planning"],
    )


def test_build_extracted_information_context_includes_populated_fields_only():
    info = ExtractedCompanyInformation(consulting_case_id="case-1", value_proposition="Best in class.")
    block = generator._build_extracted_information_context(info)

    assert "Value proposition: Best in class." in block
    assert "Products/services" not in block  # empty list -> omitted


def test_build_market_research_context_includes_competitor_notes():
    research = _make_market_research()
    block = generator._build_market_research_context(research)

    assert "Rival Inc ($35/user/month)" in block
    assert "AI-assisted planning" in block


def test_parse_diagnosis_response_maps_decision_and_findings():
    result = generator._parse_diagnosis_response("case-1", VALID_LLM_RESPONSE_MARKETING_NEEDED)

    assert result.marketing_is_recommended() is True
    assert result.confidence.value == "medium"
    assert len(result.supporting_findings) == 2
    assert result.supporting_findings[0].description == "No blog or content marketing found"


def test_parse_diagnosis_response_handles_not_marketing_decision():
    result = generator._parse_diagnosis_response("case-1", VALID_LLM_RESPONSE_NOT_MARKETING)
    assert result.marketing_is_recommended() is False
    assert "Checkout flow" in result.primary_bottleneck


def test_parse_diagnosis_response_raises_on_invalid_decision_value():
    bad_response = {**VALID_LLM_RESPONSE_MARKETING_NEEDED, "decision": "something_else"}
    with pytest.raises(Exception):
        generator._parse_diagnosis_response("case-1", bad_response)


def test_parse_diagnosis_response_raises_when_bottleneck_is_empty():
    bad_response = {**VALID_LLM_RESPONSE_MARKETING_NEEDED, "primary_bottleneck": ""}
    with pytest.raises(Exception):
        generator._parse_diagnosis_response("case-1", bad_response)


def test_analyze_company_business_case_saves_successful_diagnosis(isolated_test_database, monkeypatch):
    case = create_consulting_case(company_name="Acme Corp")

    monkeypatch.setattr(
        generator, "generate_json_response_from_main_llm",
        lambda prompt, temperature, max_output_tokens: VALID_LLM_RESPONSE_MARKETING_NEEDED,
    )

    result = generator.analyze_company_business_case(
        consulting_case_id=case.id,
        company_name="Acme Corp",
        extracted_information=_make_extracted_information(case.id),
        market_research=_make_market_research(case.id),
    )

    assert result.marketing_is_recommended() is True
    persisted = get_business_diagnosis_by_case_id(case.id)
    assert persisted is not None
    assert persisted.primary_bottleneck == result.primary_bottleneck


def test_analyze_company_business_case_raises_and_saves_nothing_on_llm_failure(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")

    def fake_failing_call(prompt, temperature, max_output_tokens):
        raise MainLlmClientError("No Gemini API key configured.")

    monkeypatch.setattr(generator, "generate_json_response_from_main_llm", fake_failing_call)

    with pytest.raises(OrchestratorError, match="Could not generate a business diagnosis"):
        generator.analyze_company_business_case(
            consulting_case_id=case.id,
            company_name="Acme Corp",
            extracted_information=_make_extracted_information(case.id),
            market_research=_make_market_research(case.id),
        )

    # Critical: no fabricated diagnosis was ever saved.
    assert get_business_diagnosis_by_case_id(case.id) is None


def test_analyze_company_business_case_raises_and_saves_nothing_on_malformed_response(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")

    malformed_response = {"decision": "marketing_is_the_primary_issue"}  # missing required fields
    monkeypatch.setattr(
        generator, "generate_json_response_from_main_llm",
        lambda prompt, temperature, max_output_tokens: malformed_response,
    )

    with pytest.raises(OrchestratorError):
        generator.analyze_company_business_case(
            consulting_case_id=case.id,
            company_name="Acme Corp",
            extracted_information=_make_extracted_information(case.id),
            market_research=_make_market_research(case.id),
        )

    assert get_business_diagnosis_by_case_id(case.id) is None


def test_analyze_company_business_case_raises_on_invalid_decision_enum_value(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")

    invalid_response = {**VALID_LLM_RESPONSE_MARKETING_NEEDED, "decision": "maybe_marketing_who_knows"}
    monkeypatch.setattr(
        generator, "generate_json_response_from_main_llm",
        lambda prompt, temperature, max_output_tokens: invalid_response,
    )

    with pytest.raises(OrchestratorError):
        generator.analyze_company_business_case(
            consulting_case_id=case.id,
            company_name="Acme Corp",
            extracted_information=_make_extracted_information(case.id),
            market_research=_make_market_research(case.id),
        )

    assert get_business_diagnosis_by_case_id(case.id) is None


def test_analyze_company_business_case_for_consulting_case_raises_when_extraction_missing(
    isolated_test_database,
):
    case = create_consulting_case(company_name="Acme Corp")

    with pytest.raises(OrchestratorError, match="no extracted company"):
        generator.analyze_company_business_case_for_consulting_case(case.id, "Acme Corp")


def test_analyze_company_business_case_for_consulting_case_raises_when_market_research_missing(
    isolated_test_database,
):
    case = create_consulting_case(company_name="Acme Corp")
    info = _make_extracted_information(case.id)
    save_extracted_information(info)

    with pytest.raises(OrchestratorError, match="no market research"):
        generator.analyze_company_business_case_for_consulting_case(case.id, "Acme Corp")


def test_analyze_company_business_case_for_consulting_case_pulls_from_storage(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")
    save_extracted_information(_make_extracted_information(case.id))
    save_market_research(_make_market_research(case.id))

    captured_prompts = []

    def fake_call(prompt, temperature, max_output_tokens):
        captured_prompts.append(prompt)
        return VALID_LLM_RESPONSE_NOT_MARKETING

    monkeypatch.setattr(generator, "generate_json_response_from_main_llm", fake_call)

    result = generator.analyze_company_business_case_for_consulting_case(case.id, "Acme Corp")

    assert result.marketing_is_recommended() is False
    assert "Acme builds project management software" in captured_prompts[0]
    assert "Rival Inc" in captured_prompts[0]
