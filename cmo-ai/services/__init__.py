"""
services
========

Non-reasoning collector and processing services.

Each service in this package has one job: fetch or transform data and
return structured domain objects. Services never make business decisions
and never decide what the final diagnosis or strategy should be — that
responsibility belongs exclusively to the orchestrator.

Implemented so far:
- website_collector_service   -> collect_website_content_for_consulting_case()
- pdf_collector_service       -> collect_pdf_content_for_consulting_case()

Planned next:
- social_media_collector_service
- market_research_service   (small LLM)
- information_extraction_service   (small LLM)
- powerpoint_generator_service
"""

from services.pdf_collector_service import collect_pdf_content_for_consulting_case
from services.website_collector_service import collect_website_content_for_consulting_case

__all__ = [
    "collect_pdf_content_for_consulting_case",
    "collect_website_content_for_consulting_case",
]
