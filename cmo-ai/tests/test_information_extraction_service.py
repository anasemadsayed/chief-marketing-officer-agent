"""
Tests for the Information Extraction Service (Brick 7).

The small LLM call itself is monkeypatched at the
`generate_json_response_from_small_llm` boundary so these tests never
hit a real API, matching the pattern used for Market Research (Brick 6).
"""

from __future__ import annotations

from domain import (
    CollectedSource,
    CompetitorProfile,
    InformationSourceType,
    MarketResearch,
)
from services import information_extraction_service as service
from services.small_llm_client import SmallLlmClientError
from storage.collected_source_repository import save_collected_source
from storage.consulting_case_repository import create_consulting_case
from storage.extracted_company_information_repository import get_extracted_information_by_case_id
from storage.market_research_repository import save_market_research

VALID_LLM_RESPONSE = {
    "company_description_summary": "Acme Corp builds project management software for remote teams.",
    "products_and_services": ["Project tracker", "Time billing"],
    "value_proposition": "The only PM tool built for distributed teams.",
    "unique_selling_points": ["Async-first workflows"],
    "target_audience_signals": ["Remote-first companies"],
    "pricing_information": ["$29/user/month"],
    "contact_information": ["hello@acme.example"],
    "notable_content_snippets": ["We believe great work happens anywhere."],
}


def _make_source(
    text: str,
    source_type: InformationSourceType = InformationSourceType.COMPANY_WEBSITE,
    successful: bool = True,
) -> CollectedSource:
    return CollectedSource(
        id=f"src-{hash(text) % 10000}",
        consulting_case_id="case-1",
        source_type=source_type,
        source_url_or_path="https://acme.example.com",
        raw_content=text,
        collection_successful=successful,
    )


def _make_market_research() -> MarketResearch:
    return MarketResearch(
        consulting_case_id="case-1",
        industry_overview="B2B SaaS project management",
        competitors=[CompetitorProfile(name="Rival Inc")],
        target_audience_characteristics=["Mid-market teams"],
        market_trends=["AI-assisted planning"],
    )


def test_build_raw_sources_context_includes_only_successful_sources_with_labels():
    sources = [
        _make_source("About Acme: we build tools.", InformationSourceType.COMPANY_WEBSITE),
        _make_source("Failed fetch text", successful=False),
        _make_source("Founded 2020.", InformationSourceType.UPLOADED_PDF),
    ]
    context = service._build_raw_sources_context(sources)

    assert "[Source: company_website" in context
    assert "About Acme" in context
    assert "[Source: uploaded_pdf" in context
    assert "Founded 2020." in context
    assert "Failed fetch text" not in context


def test_build_raw_sources_context_truncates_long_content():
    sources = [_make_source("x" * 50000)]
    context = service._build_raw_sources_context(sources, max_characters=200)

    assert len(context) <= 260
    assert context.endswith("(truncated)")


def test_build_market_research_summary_block_returns_empty_for_none():
    assert service._build_market_research_summary_block(None) == ""


def test_build_market_research_summary_block_includes_populated_fields_only():
    research = MarketResearch(consulting_case_id="case-1", industry_overview="B2B SaaS")
    block = service._build_market_research_summary_block(research)

    assert "Industry: B2B SaaS" in block
    assert "Known competitors" not in block  # empty list -> omitted


def test_build_market_research_summary_block_includes_competitors_and_trends():
    block = service._build_market_research_summary_block(_make_market_research())

    assert "Rival Inc" in block
    assert "AI-assisted planning" in block


def test_build_information_extraction_prompt_includes_company_and_raw_content():
    prompt = service._build_information_extraction_prompt("Acme Corp", "raw website text here", "")
    assert "Acme Corp" in prompt
    assert "raw website text here" in prompt


def test_build_information_extraction_prompt_mentions_market_research_when_present():
    prompt = service._build_information_extraction_prompt("Acme Corp", "raw text", "Industry: B2B SaaS\n")
    assert "and market research" in prompt
    assert "Industry: B2B SaaS" in prompt


def test_parse_extraction_response_maps_all_fields():
    result = service._parse_extraction_response("case-1", VALID_LLM_RESPONSE)

    assert result.consulting_case_id == "case-1"
    assert result.company_description_summary == VALID_LLM_RESPONSE["company_description_summary"]
    assert result.products_and_services == ["Project tracker", "Time billing"]
    assert result.pricing_information == ["$29/user/month"]


def test_parse_extraction_response_raises_when_list_field_is_wrong_type():
    bad_response = {**VALID_LLM_RESPONSE, "products_and_services": "not a list"}
    try:
        service._parse_extraction_response("case-1", bad_response)
        assert False, "expected TypeError"
    except TypeError as error:
        assert "products_and_services" in str(error)


def test_extract_useful_business_information_saves_successful_result(isolated_test_database, monkeypatch):
    case = create_consulting_case(company_name="Acme Corp")
    sources = [_make_source("About Acme: project management software.")]

    monkeypatch.setattr(
        service, "generate_json_response_from_small_llm", lambda prompt, temperature: VALID_LLM_RESPONSE
    )

    result = service.extract_useful_business_information(
        consulting_case_id=case.id, company_name="Acme Corp", collected_sources=sources
    )

    assert result.company_description_summary == VALID_LLM_RESPONSE["company_description_summary"]
    assert result.products_and_services == ["Project tracker", "Time billing"]

    persisted = get_extracted_information_by_case_id(case.id)
    assert persisted is not None
    assert persisted.value_proposition == VALID_LLM_RESPONSE["value_proposition"]


def test_extract_useful_business_information_skips_llm_call_when_no_content_collected(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")

    llm_was_called = False

    def fake_call(prompt, temperature):
        nonlocal llm_was_called
        llm_was_called = True
        return VALID_LLM_RESPONSE

    monkeypatch.setattr(service, "generate_json_response_from_small_llm", fake_call)

    # No sources at all, and a source that failed to collect.
    failed_source = _make_source("irrelevant", successful=False)
    result = service.extract_useful_business_information(
        consulting_case_id=case.id, company_name="Acme Corp", collected_sources=[failed_source]
    )

    assert llm_was_called is False
    assert "No collected source content" in result.company_description_summary
    assert result.products_and_services == []


def test_extract_useful_business_information_degrades_gracefully_on_llm_failure(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")
    sources = [_make_source("About Acme: we build tools.")]

    def fake_failing_call(prompt, temperature):
        raise SmallLlmClientError("No Gemini API key configured.")

    monkeypatch.setattr(service, "generate_json_response_from_small_llm", fake_failing_call)

    result = service.extract_useful_business_information(
        consulting_case_id=case.id, company_name="Acme Corp", collected_sources=sources
    )

    assert "could not be completed" in result.company_description_summary
    assert result.products_and_services == []

    persisted = get_extracted_information_by_case_id(case.id)
    assert persisted is not None


def test_extract_useful_business_information_degrades_gracefully_on_malformed_response(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")
    sources = [_make_source("About Acme: we build tools.")]

    malformed = {"products_and_services": {"not": "a list"}}
    monkeypatch.setattr(service, "generate_json_response_from_small_llm", lambda prompt, temperature: malformed)

    result = service.extract_useful_business_information(
        consulting_case_id=case.id, company_name="Acme Corp", collected_sources=sources
    )

    assert "could not be completed" in result.company_description_summary


def test_extract_useful_business_information_for_consulting_case_pulls_from_storage(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")
    source = _make_source("About Acme: project management software.")
    source.consulting_case_id = case.id
    save_collected_source(source)

    research = _make_market_research()
    research.consulting_case_id = case.id
    save_market_research(research)

    captured_prompts = []

    def fake_call(prompt, temperature):
        captured_prompts.append(prompt)
        return VALID_LLM_RESPONSE

    monkeypatch.setattr(service, "generate_json_response_from_small_llm", fake_call)

    result = service.extract_useful_business_information_for_consulting_case(
        consulting_case_id=case.id, company_name="Acme Corp"
    )

    assert result.company_description_summary == VALID_LLM_RESPONSE["company_description_summary"]
    assert "project management software" in captured_prompts[0]
    assert "Rival Inc" in captured_prompts[0]
