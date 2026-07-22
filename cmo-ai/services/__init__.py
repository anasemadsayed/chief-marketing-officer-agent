"""
services
========

Non-reasoning collector and processing services.

Each service in this package has one job: fetch or transform data and
return a structured domain object. Services never make business decisions
and never decide what the final diagnosis or strategy should be — that
responsibility belongs exclusively to the orchestrator.

Planned services (built brick by brick):
- website_collector_service
- pdf_collector_service
- social_media_collector_service
- market_research_service   (small LLM)
- information_extraction_service   (small LLM)
- powerpoint_generator_service
"""
