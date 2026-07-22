"""
Shared enumerations used across the domain layer.

Keeping these in one place avoids magic strings scattered through
services, the orchestrator, and the storage layer.
"""

from __future__ import annotations

from enum import Enum


class ConsultingCaseStatus(str, Enum):
    """Lifecycle state of a single consulting engagement."""

    CREATED = "created"
    COLLECTING_INFORMATION = "collecting_information"
    PERFORMING_MARKET_RESEARCH = "performing_market_research"
    EXTRACTING_INFORMATION = "extracting_information"
    DIAGNOSING_BUSINESS_CASE = "diagnosing_business_case"
    GENERATING_STRATEGY = "generating_strategy"
    COMPLETED = "completed"
    FAILED = "failed"


class InformationSourceType(str, Enum):
    """Where a piece of collected raw information came from."""

    COMPANY_WEBSITE = "company_website"
    UPLOADED_PDF = "uploaded_pdf"
    LINKEDIN_PROFILE = "linkedin_profile"
    FACEBOOK_PROFILE = "facebook_profile"
    INSTAGRAM_PROFILE = "instagram_profile"
    ADDITIONAL_LINK = "additional_link"


class MarketingNecessityDecision(str, Enum):
    """The orchestrator's core yes/no decision on the diagnosis."""

    MARKETING_IS_THE_PRIMARY_ISSUE = "marketing_is_the_primary_issue"
    MARKETING_IS_NOT_THE_PRIMARY_ISSUE = "marketing_is_not_the_primary_issue"


class ConfidenceLevel(str, Enum):
    """How confident the orchestrator is in a finding or decision."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class StrategyGenerationReason(str, Enum):
    """Why a MarketingStrategy object exists for a given case."""

    DIAGNOSIS_RECOMMENDED_MARKETING = "diagnosis_recommended_marketing"
    USER_REQUESTED_STRATEGY_DESPITE_DIAGNOSIS = "user_requested_strategy_despite_diagnosis"


class ReportType(str, Enum):
    """What kind of final report was produced for a case."""

    DIAGNOSIS_ONLY = "diagnosis_only"
    DIAGNOSIS_AND_STRATEGY = "diagnosis_and_strategy"
