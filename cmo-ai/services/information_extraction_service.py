"""
Information Extraction Service.

The last service in the pipeline before the orchestrator takes over.
Wraps the small free LLM to turn all raw collected data — website pages,
PDF text, social media previews — plus the already-structured market
research, into one clean ExtractedCompanyInformation record: noise
removed, duplicates collapsed, only meaningful business information
kept.

Like the other services, this one does NOT perform business reasoning,
diagnosis, or give recommendations — it only cleans and structures what
was already collected. Any failure degrades gracefully rather than
crashing the case pipeline.
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import ValidationError

from config.settings import settings
from domain import CollectedSource, ExtractedCompanyInformation, MarketResearch
from services.small_llm_client import SmallLlmClientError, generate_json_response_from_small_llm
from storage.collected_source_repository import list_collected_sources_for_case
from storage.extracted_company_information_repository import save_extracted_information
from storage.market_research_repository import get_market_research_by_case_id

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT_TEMPLATE = """\
You are a data cleaning and information extraction specialist. Below is \
raw, noisy content collected from a company's website, PDF documents, \
and/or social media profiles{market_research_note}. Your job is to extract \
ONLY the meaningful, business-relevant information and discard everything \
else: navigation menus, cookie banners, login prompts, ads, repeated \
boilerplate, social media icon lists, copyright footers, and any \
duplicated content.

Return ONLY a JSON object (no markdown formatting, no commentary) with \
exactly this shape:

{{
  "company_description_summary": "2-4 sentence clean summary of what the company does",
  "products_and_services": ["product/service one", "..."],
  "value_proposition": "what the company claims makes it worth choosing, in its own words",
  "unique_selling_points": ["USP one", "..."],
  "target_audience_signals": ["explicit or implicit statement about who they serve", "..."],
  "pricing_information": ["any pricing/plan/packaging detail found", "..."],
  "contact_information": ["email, phone, or address found", "..."],
  "notable_content_snippets": ["short meaningful excerpt worth preserving as evidence (e.g. mission statement, testimonial), under ~200 characters each", "..."]
}}

Rules:
- Do not invent information that isn't present in the raw content below. If \
a field has nothing useful to report, return an empty string (or empty \
list) for it rather than guessing.
- Deduplicate: if the same fact appears multiple times across sources, \
report it once.
- Do not perform business analysis, diagnosis, or give recommendations — \
that is not your job. Only extract and clean.
- Keep each list item concise.

Company name: {company_name}
{market_research_block}
Raw collected content:
{raw_sources_context}"""


def extract_useful_business_information(
    consulting_case_id: str,
    company_name: str,
    collected_sources: list[CollectedSource],
    market_research: Optional[MarketResearch] = None,
) -> ExtractedCompanyInformation:
    """
    Clean and structure all raw collected data for one consulting case
    into a single ExtractedCompanyInformation record, saving it.

    If nothing was successfully collected, the LLM is never called — an
    honest, empty record is saved instead, noting that no source content
    was available. If the LLM call fails or returns something unusable,
    the pipeline still doesn't crash: a record is saved with the failure
    explained in `company_description_summary`.
    """
    raw_sources_context = _build_raw_sources_context(collected_sources)

    if not raw_sources_context.strip():
        logger.warning(
            "No successfully collected raw content available for case=%s; skipping extraction LLM call",
            consulting_case_id,
        )
        extracted_information = ExtractedCompanyInformation(
            consulting_case_id=consulting_case_id,
            company_description_summary="No collected source content was available to extract information from.",
        )
        save_extracted_information(extracted_information)
        return extracted_information

    market_research_block = _build_market_research_summary_block(market_research)
    prompt = _build_information_extraction_prompt(company_name, raw_sources_context, market_research_block)

    try:
        response_data = generate_json_response_from_small_llm(
            prompt, temperature=settings.information_extraction_llm_temperature
        )
        extracted_information = _parse_extraction_response(consulting_case_id, response_data)
    except (SmallLlmClientError, ValidationError, TypeError) as error:
        logger.warning("Information extraction failed for case=%s: %s", consulting_case_id, error)
        extracted_information = ExtractedCompanyInformation(
            consulting_case_id=consulting_case_id,
            company_description_summary=f"Information extraction could not be completed: {error}",
        )

    save_extracted_information(extracted_information)
    return extracted_information


def extract_useful_business_information_for_consulting_case(
    consulting_case_id: str,
    company_name: str,
) -> ExtractedCompanyInformation:
    """
    Convenience entry point for the main pipeline: pulls whatever was
    already collected and researched (Bricks 4/5/6) straight from
    storage, so the caller doesn't need to assemble it manually.
    """
    collected_sources = list_collected_sources_for_case(consulting_case_id)
    market_research = get_market_research_by_case_id(consulting_case_id)

    return extract_useful_business_information(
        consulting_case_id=consulting_case_id,
        company_name=company_name,
        collected_sources=collected_sources,
        market_research=market_research,
    )


def _build_raw_sources_context(
    collected_sources: list[CollectedSource],
    max_characters: Optional[int] = None,
) -> str:
    """
    Concatenate raw content from successfully collected sources, each
    labeled with its origin, truncated to a safe overall length. Pure
    mechanical assembly — no summarization or interpretation.
    """
    max_characters = (
        max_characters if max_characters is not None else settings.information_extraction_max_context_characters
    )

    blocks = [
        f"[Source: {source.source_type.value} | {source.source_url_or_path}]\n{source.raw_content}"
        for source in collected_sources
        if source.collection_successful and source.raw_content
    ]
    combined = "\n\n".join(blocks)

    if len(combined) > max_characters:
        combined = combined[:max_characters] + "\n...(truncated)"

    return combined


def _build_market_research_summary_block(market_research: Optional[MarketResearch]) -> str:
    """Render the already-structured MarketResearch object as plain text context for the prompt."""
    if market_research is None:
        return ""

    lines: list[str] = []
    if market_research.industry_overview:
        lines.append(f"Industry: {market_research.industry_overview}")
    if market_research.competitors:
        competitor_names = ", ".join(competitor.name for competitor in market_research.competitors)
        lines.append(f"Known competitors: {competitor_names}")
    if market_research.target_audience_characteristics:
        lines.append(
            "Market-level audience traits: " + "; ".join(market_research.target_audience_characteristics)
        )
    if market_research.market_trends:
        lines.append("Market trends: " + "; ".join(market_research.market_trends))

    if not lines:
        return ""

    return "Market research context (already gathered, for reference only):\n" + "\n".join(lines) + "\n"


def _build_information_extraction_prompt(
    company_name: str, raw_sources_context: str, market_research_block: str
) -> str:
    market_research_note = " and market research" if market_research_block else ""
    return _EXTRACTION_PROMPT_TEMPLATE.format(
        company_name=company_name,
        market_research_note=market_research_note,
        market_research_block=market_research_block,
        raw_sources_context=raw_sources_context,
    )


def _parse_extraction_response(consulting_case_id: str, data: dict) -> ExtractedCompanyInformation:
    """Map the LLM's raw JSON dict onto a validated ExtractedCompanyInformation domain object."""
    list_field_names = (
        "products_and_services",
        "unique_selling_points",
        "target_audience_signals",
        "pricing_information",
        "contact_information",
        "notable_content_snippets",
    )

    parsed_lists: dict[str, list[str]] = {}
    for field_name in list_field_names:
        value = data.get(field_name) or []
        if not isinstance(value, list):
            raise TypeError(f"Expected '{field_name}' to be a list, got {type(value).__name__}")
        parsed_lists[field_name] = [str(item) for item in value]

    return ExtractedCompanyInformation(
        consulting_case_id=consulting_case_id,
        company_description_summary=data.get("company_description_summary") or "",
        value_proposition=data.get("value_proposition") or "",
        **parsed_lists,
    )
