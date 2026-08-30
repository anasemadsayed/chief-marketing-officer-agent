"""
services
========

Non-reasoning collector and processing services.

Each service in this package has one job: fetch or transform data and
return structured domain objects. Services never make business decisions
and never decide what the final diagnosis or strategy should be — that
responsibility belongs exclusively to the orchestrator.

Implemented so far:
- website_collector_service      -> collect_website_content_for_consulting_case()
- pdf_collector_service          -> collect_pdf_content_for_consulting_case()
- social_media_collector_service -> collect_social_media_profiles_for_consulting_case()
- small_llm_client                -> generate_json_response_from_small_llm()
- market_research_service        -> perform_market_and_competitor_research()

Planned next:
- information_extraction_service   (small LLM)
- powerpoint_generator_service
"""

from services.market_research_service import (
    perform_market_and_competitor_research,
    perform_market_and_competitor_research_for_consulting_case,
)
from services.pdf_collector_service import collect_pdf_content_for_consulting_case
from services.small_llm_client import SmallLlmClientError, generate_json_response_from_small_llm
from services.social_media_collector_service import (
    collect_social_media_profile_content,
    collect_social_media_profiles_for_consulting_case,
)
from services.website_collector_service import collect_website_content_for_consulting_case

__all__ = [
    "SmallLlmClientError",
    "collect_pdf_content_for_consulting_case",
    "collect_social_media_profile_content",
    "collect_social_media_profiles_for_consulting_case",
    "collect_website_content_for_consulting_case",
    "generate_json_response_from_small_llm",
    "perform_market_and_competitor_research",
    "perform_market_and_competitor_research_for_consulting_case",
]