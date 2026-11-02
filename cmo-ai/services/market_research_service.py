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
You are a senior market intelligence director conducting competitive and market research for the target company.
Analyze the target company, identify its exact market niche, regional landscape (e.g. geographic focus like Egypt/MENA/Global), and produce actionable, high-depth competitive intelligence.

Return ONLY a JSON object (no markdown formatting, no commentary, no explanation) with exactly this shape:

{{
  "industry_overview": "Comprehensive 3-5 sentence analysis of the industry sector, current market size/dynamics, growth drivers, and regional nuances for this business.",
  "competitors": [
    {{
      "name": "Direct Competitor Name",
      "website_url": "https://example.com",
      "notes": "Detailed breakdown: value proposition, pricing models/ranges, target market overlap, marketing channels used (SEO, Meta ads, influencers, offline), and their competitive advantage vs the target company."
    }}
  ],
  "target_audience_characteristics": [
    "Specific demographic, socioeconomic profile, and student/customer personas (e.g., career switchers, fresh grads, corporate teams)",
    "Core pain points and buying motivations (e.g., high barrier to entry, price sensitivity, demand for job placement guarantees)",
    "Decision-making criteria and primary research channels used by buyers"
  ],
  "market_trends": [
    "Macro shift or technological trend impacting customer demand in this specific niche",
    "Pricing and payment trends (e.g., installments, ISAs, subscription vs upfront tuition)",
    "Customer acquisition channel effectiveness and shifts in this industry"
  ],
  "additional_notes": [
    "Key regulatory, economic, or competitive threats specific to this company's operating market",
    "Identified gaps in the market that competitors are failing to address"
  ]
}}

Rules:
- Be specific, detailed, and realistic. Avoid vague generalities like 'they face competition from online platforms'. Name real competitors operating in the exact same market and segment.
- If the company is regional (e.g. Egyptian tech academy, local SaaS, regional e-commerce), prioritize direct local & regional competitors who fight for the exact same customers.
- List 4 to 6 real, prominent competitors with thorough positioning notes.
- Do not output empty placeholders. Populate every field with concrete market intelligence based on the company's real sector.

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
