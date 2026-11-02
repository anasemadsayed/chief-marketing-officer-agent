"""
services
========

Non-reasoning collector, processing, and rendering services.

Each service in this package has one job: fetch, transform, or render
data and return structured domain objects (or, for the PowerPoint
generator, a rendered file). Services never make business decisions and
never decide what the final diagnosis or strategy should be — that
responsibility belongs exclusively to the orchestrator.

Implemented (all services complete for V1 — this is the last brick
before end-to-end pipeline wiring):
- website_collector_service          -> collect_website_content_for_consulting_case()
- pdf_collector_service              -> collect_pdf_content_for_consulting_case()
- social_media_collector_service     -> collect_social_media_profiles_for_consulting_case()
- agent_reach_client                 -> fetch_social_profile_via_agent_reach()
- small_llm_client                    -> generate_json_response_from_small_llm()
- market_research_service            -> perform_market_and_competitor_research()
- information_extraction_service     -> extract_useful_business_information()
- powerpoint_generator_service       -> create_business_consulting_presentation()
                                         (handles both DIAGNOSIS_ONLY and
                                         DIAGNOSIS_AND_STRATEGY reports, including
                                         the override-disclaimer slide)

Planned next:
- api/ + main.py wiring (Brick 11): the end-to-end pipeline tying every
  brick together
"""

from services.agent_reach_client import (
    fetch_social_profile_via_agent_reach,
    is_agent_reach_available,
)
from services.information_extraction_service import (
    extract_useful_business_information,
    extract_useful_business_information_for_consulting_case,
)
from services.market_research_service import (
    perform_market_and_competitor_research,
    perform_market_and_competitor_research_for_consulting_case,
)
from services.pdf_collector_service import collect_pdf_content_for_consulting_case
from services.powerpoint_generator_service import (
    PowerPointGenerationError,
    create_business_consulting_presentation,
    create_business_consulting_presentation_for_consulting_case,
)
from services.small_llm_client import SmallLlmClientError, generate_json_response_from_small_llm
from services.social_media_collector_service import (
    collect_social_media_profile_content,
    collect_social_media_profiles_for_consulting_case,
)
from services.website_collector_service import collect_website_content_for_consulting_case

__all__ = [
    "PowerPointGenerationError",
    "SmallLlmClientError",
    "collect_pdf_content_for_consulting_case",
    "collect_social_media_profile_content",
    "collect_social_media_profiles_for_consulting_case",
    "collect_website_content_for_consulting_case",
    "create_business_consulting_presentation",
    "create_business_consulting_presentation_for_consulting_case",
    "extract_useful_business_information",
    "extract_useful_business_information_for_consulting_case",
    "fetch_social_profile_via_agent_reach",
    "generate_json_response_from_small_llm",
    "is_agent_reach_available",
    "perform_market_and_competitor_research",
    "perform_market_and_competitor_research_for_consulting_case",
]

