"""
Market Research Service.

Wraps the small free LLM to gather structured market intelligence:
competitors, industry overview, target audience characteristics, and
market trends. This service does NOT perform business reasoning or
give strategic advice — it only reports what it can find, the same way
the collector services only fetch, never judge.

Any failure (missing API key, network error, malformed response) is
handled gracefully: the case pipeline never crashes because the free
LLM had a bad day. Instead an honest, mostly-empty MarketResearch
record is saved with the failure explained in `additional_notes`.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from config.settings import settings
from domain import CollectedSource, CompetitorProfile, MarketResearch
from services.small_llm_client import SmallLlmClientError, generate_json_response_from_small_llm
from storage.market_research_repository import save_market_research

logger = logging.getLogger(__name__)

_MARKET_RESEARCH_PROMPT_TEMPLATE = """\
You are a market research analyst. Research the company described below \
and return ONLY a JSON object (no markdown formatting, no commentary, no \
explanation) with exactly this shape:

{{
  "industry_overview": "1-3 sentence description of the industry this company operates in",
  "competitors": [
    {{"name": "Competitor Name", "website_url": "https://example.com", "notes": "short positioning notes"}}
  ],
  "target_audience_characteristics": ["trait one", "trait two"],
  "market_trends": ["trend one", "trend two"],
  "additional_notes": ["any other useful, publicly available business intelligence"]
}}

Rules:
- Only report factual, publicly known market information. Do not give \
strategic advice, opinions, or recommendations — that is not your job.
- List 3-6 real, named competitors if you can identify them with reasonable \
confidence. If you are not confident about specific competitors, say so in \
additional_notes instead of inventing names.
- "website_url" may be null if you don't know it. "notes" may be null.
- Keep each list item concise (one sentence or less).
- If a field has nothing useful to report, return an empty list (or empty \
string for industry_overview) rather than omitting the field.

Company name: {company_name}
{business_context_block}"""


def perform_market_and_competitor_research(
    consulting_case_id: str,
    company_name: str,
    business_context: str = "",
) -> MarketResearch:
    """
    Ask the small LLM to research this company's market, parse and
    persist the result.

    `business_context` is optional free text (e.g. a snippet of the
    company's raw website content) that helps the model understand what
    the company actually does before it goes looking for competitors.
    """
    prompt = _build_market_research_prompt(company_name, business_context)

    try:
        response_data = generate_json_response_from_small_llm(
            prompt, temperature=settings.market_research_llm_temperature
        )
        market_research = _parse_market_research_response(consulting_case_id, response_data)
    except (SmallLlmClientError, ValidationError, TypeError) as error:
        logger.warning("Market research failed for case=%s: %s", consulting_case_id, error)
        market_research = MarketResearch(
            consulting_case_id=consulting_case_id,
            additional_notes=[f"Market research could not be completed: {error}"],
        )

    save_market_research(market_research)
    return market_research


def perform_market_and_competitor_research_for_consulting_case(
    consulting_case_id: str,
    company_name: str,
    collected_sources: list[CollectedSource],
) -> MarketResearch:
    """
    Convenience entry point for the main pipeline: builds business
    context out of whatever was already collected (Bricks 4/5) and runs
    research from that, without the caller needing to assemble the
    context text itself.
    """
    business_context = _build_business_context_summary(collected_sources)
    return perform_market_and_competitor_research(consulting_case_id, company_name, business_context)


def _build_business_context_summary(
    collected_sources: list[CollectedSource],
    max_characters: int | None = None,
) -> str:
    """
    Concatenate raw content from successfully collected sources into one
    context block for the prompt, truncated to a safe length. Pure
    mechanical truncation — no summarization or interpretation.
    """
    max_characters = max_characters if max_characters is not None else settings.market_research_max_context_characters

    successful_texts = [
        source.raw_content for source in collected_sources if source.collection_successful and source.raw_content
    ]
    combined = "\n\n".join(successful_texts)

    if len(combined) > max_characters:
        combined = combined[:max_characters] + "\n...(truncated)"

    return combined


def _build_market_research_prompt(company_name: str, business_context: str) -> str:
    business_context_block = (
        f"\nWhat we already know about the company (raw, possibly noisy website content):\n{business_context}"
        if business_context.strip()
        else ""
    )
    return _MARKET_RESEARCH_PROMPT_TEMPLATE.format(
        company_name=company_name,
        business_context_block=business_context_block,
    )


def _parse_market_research_response(consulting_case_id: str, data: dict) -> MarketResearch:
    """Map the LLM's raw JSON dict onto a validated MarketResearch domain object."""
    competitors_raw = data.get("competitors") or []
    if not isinstance(competitors_raw, list):
        raise TypeError(f"Expected 'competitors' to be a list, got {type(competitors_raw).__name__}")

    competitors = [CompetitorProfile(**competitor) for competitor in competitors_raw]

    return MarketResearch(
        consulting_case_id=consulting_case_id,
        industry_overview=data.get("industry_overview") or "",
        competitors=competitors,
        target_audience_characteristics=data.get("target_audience_characteristics") or [],
        market_trends=data.get("market_trends") or [],
        additional_notes=data.get("additional_notes") or [],
    )
