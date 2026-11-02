"""
Tests for the Market Research Service (Brick 6).

The small LLM call itself is monkeypatched at the
`generate_json_response_from_small_llm` boundary so these tests never
hit a real API, matching the pattern used for the collector services.
"""

from __future__ import annotations

from domain import CollectedSource, InformationSourceType
from services import market_research_service as service
from services.small_llm_client import SmallLlmClientError
from storage.consulting_case_repository import create_consulting_case
from storage.market_research_repository import get_market_research_by_case_id

VALID_LLM_RESPONSE = {
    "industry_overview": "B2B project management SaaS for growing teams.",
    "competitors": [
        {"name": "Rival Inc", "website_url": "https://rival.example.com", "notes": "Enterprise-focused."},
        {"name": "Other Co", "website_url": None, "notes": None},
    ],
    "target_audience_characteristics": ["Mid-market companies", "Remote-first teams"],
    "market_trends": ["Shift toward AI-assisted planning"],
    "additional_notes": ["Category is fairly saturated"],
}


def _make_source(text: str, successful: bool = True) -> CollectedSource:
    return CollectedSource(
        id="src-1",
        consulting_case_id="case-1",
        source_type=InformationSourceType.COMPANY_WEBSITE,
        source_url_or_path="https://acme.example.com",
        raw_content=text,
        collection_successful=successful,
    )


def test_build_business_context_summary_concatenates_successful_sources_only():
    sources = [
        _make_source("About Acme: we build tools.", successful=True),
        _make_source("This one failed", successful=False),
        _make_source("Contact us at hello@acme.example", successful=True),
    ]
    context = service._build_business_context_summary(sources)

    assert "About Acme" in context
    assert "Contact us" in context
    assert "This one failed" not in context


def test_build_business_context_summary_truncates_long_content():
    long_text = "x" * 10000
    sources = [_make_source(long_text)]
    context = service._build_business_context_summary(sources, max_characters=100)

    assert len(context) <= 120
    assert context.endswith("(truncated)")


def test_build_market_research_prompt_includes_company_name_and_context():
    prompt = service._build_market_research_prompt("Acme Corp", "We build tools.")
    assert "Acme Corp" in prompt
    assert "We build tools." in prompt


def test_build_market_research_prompt_omits_context_block_when_empty():
    prompt = service._build_market_research_prompt("Acme Corp", "")
    assert "Acme Corp" in prompt
    assert "What we already know" not in prompt


def test_parse_market_research_response_maps_all_fields():
    result = service._parse_market_research_response("case-1", VALID_LLM_RESPONSE)

    assert result.consulting_case_id == "case-1"
    assert result.industry_overview == VALID_LLM_RESPONSE["industry_overview"]
    assert len(result.competitors) == 2
    assert result.competitors[0].name == "Rival Inc"
    assert result.competitors[1].website_url is None
    assert result.market_trends == ["Shift toward AI-assisted planning"]


def test_perform_market_and_competitor_research_saves_successful_result(isolated_test_database, monkeypatch):
    case = create_consulting_case(company_name="Acme Corp")

    monkeypatch.setattr(service, "generate_json_response_from_small_llm", lambda prompt, temperature: VALID_LLM_RESPONSE)

    result = service.perform_market_and_competitor_research(
        consulting_case_id=case.id, company_name="Acme Corp", business_context="We build tools."
    )

    assert result.industry_overview == VALID_LLM_RESPONSE["industry_overview"]
    assert len(result.competitors) == 2

    persisted = get_market_research_by_case_id(case.id)
    assert persisted is not None
    assert persisted.competitors[0].name == "Rival Inc"


def test_perform_market_and_competitor_research_degrades_gracefully_on_llm_failure(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")

    def fake_failing_call(prompt, temperature):
        raise SmallLlmClientError("No Gemini API key configured.")

    monkeypatch.setattr(service, "generate_json_response_from_small_llm", fake_failing_call)

    result = service.perform_market_and_competitor_research(
        consulting_case_id=case.id, company_name="Acme Corp"
    )

    assert result.industry_overview == ""
    assert result.competitors == []
    assert len(result.additional_notes) == 1
    assert "could not be completed" in result.additional_notes[0]

    # The pipeline never crashes: a (mostly empty) record is still persisted.
    persisted = get_market_research_by_case_id(case.id)
    assert persisted is not None


def test_perform_market_and_competitor_research_degrades_gracefully_on_malformed_response(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")

    malformed_response = {"competitors": "this should be a list, not a string"}
    monkeypatch.setattr(service, "generate_json_response_from_small_llm", lambda prompt, temperature: malformed_response)

    result = service.perform_market_and_competitor_research(
        consulting_case_id=case.id, company_name="Acme Corp"
    )

    assert "could not be completed" in result.additional_notes[0]


def test_perform_market_and_competitor_research_for_consulting_case_builds_context_from_sources(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")
    sources = [_make_source("Acme builds project management software.", successful=True)]

    captured_prompts = []

    def fake_call(prompt, temperature):
        captured_prompts.append(prompt)
        return VALID_LLM_RESPONSE

    monkeypatch.setattr(service, "generate_json_response_from_small_llm", fake_call)

    result = service.perform_market_and_competitor_research_for_consulting_case(
        consulting_case_id=case.id, company_name="Acme Corp", collected_sources=sources
    )

    assert result.industry_overview == VALID_LLM_RESPONSE["industry_overview"]
    assert "project management software" in captured_prompts[0]
