"""
domain
======

Pure data models for cmoAI (Pydantic models / dataclasses only).

This package defines the shared vocabulary of the whole system:
CompanyProfile, CollectedSource, ExtractedCompanyInformation,
MarketResearch, Finding, BusinessDiagnosis, MarketingStrategy,
ConsultingCase, GeneratedReport, etc.

Rules for this package:
- No business logic.
- No I/O (no HTTP calls, no database calls, no file reads).
- No LLM calls.
- Only typed data structures and their validation rules.

Every service and the orchestrator communicate exclusively through
these models.
"""
"""
domain
======

Pure data models for cmoAI (Pydantic models only) — the shared vocabulary
of the whole system.

Rules for this package:
- No business logic beyond simple, self-contained validation/convenience
  methods on the models themselves (e.g. `marketing_is_recommended()`).
- No I/O (no HTTP calls, no database calls, no file reads).
- No LLM calls.

Every service and the orchestrator communicate exclusively through
these models.
"""

from domain.business_diagnosis import BusinessDiagnosis
from domain.collected_source import CollectedSource
from domain.company_profile import CompanyProfile
from domain.consulting_case import ConsultingCase
from domain.enums import (
    ConfidenceLevel,
    ConsultingCaseStatus,
    InformationSourceType,
    MarketingNecessityDecision,
    ReportType,
    StrategyGenerationReason,
)
from domain.extracted_company_information import ExtractedCompanyInformation
from domain.finding import Finding
from domain.generated_report import GeneratedReport
from domain.market_research import CompetitorProfile, MarketResearch
from domain.marketing_strategy import MarketingStrategy, StrategyInitiative

__all__ = [
    "BusinessDiagnosis",
    "CollectedSource",
    "CompanyProfile",
    "CompetitorProfile",
    "ConfidenceLevel",
    "ConsultingCase",
    "ConsultingCaseStatus",
    "ExtractedCompanyInformation",
    "Finding",
    "GeneratedReport",
    "InformationSourceType",
    "MarketResearch",
    "MarketingNecessityDecision",
    "MarketingStrategy",
    "ReportType",
    "StrategyGenerationReason",
    "StrategyInitiative",
]
