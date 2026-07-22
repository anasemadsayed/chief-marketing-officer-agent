"""
Tests for the domain models (Brick 2).

These tests don't touch any I/O or LLMs — they only prove that:
1. Every model can be constructed with realistic data.
2. The cross-field business rules baked into the models themselves
   (override warning requirement, report_type/strategy consistency)
   are actually enforced.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain import (
    BusinessDiagnosis,
    CollectedSource,
    CompanyProfile,
    CompetitorProfile,
    ConfidenceLevel,
    ConsultingCase,
    ConsultingCaseStatus,
    ExtractedCompanyInformation,
    Finding,
    GeneratedReport,
    InformationSourceType,
    MarketResearch,
    MarketingNecessityDecision,
    MarketingStrategy,
    ReportType,
    StrategyGenerationReason,
    StrategyInitiative,
)

CASE_ID = "acme-corp-9f8a2b"


def build_sample_finding() -> Finding:
    return Finding(
        description="Website checkout has a 68% drop-off rate",
        evidence="Analytics screenshot shows 68% cart abandonment over 30 days",
        source_reference="uploaded_pdf:analytics_report",
        confidence=ConfidenceLevel.HIGH,
    )


def test_consulting_case_can_be_created_with_minimal_input():
    case = ConsultingCase(id=CASE_ID, company_name="Acme Corp", website_url="https://acme.example.com")
    assert case.status == ConsultingCaseStatus.CREATED
    assert case.has_at_least_one_input_source() is True


def test_consulting_case_detects_missing_input_sources():
    case = ConsultingCase(id=CASE_ID, company_name="Acme Corp")
    assert case.has_at_least_one_input_source() is False


def test_company_profile_and_collected_source_share_the_same_case_id():
    profile = CompanyProfile(
        consulting_case_id=CASE_ID,
        company_name="Acme Corp",
        industry="B2B SaaS",
        website_url="https://acme.example.com",
    )
    source = CollectedSource(
        id="src-001",
        consulting_case_id=CASE_ID,
        source_type=InformationSourceType.COMPANY_WEBSITE,
        source_url_or_path="https://acme.example.com/about",
        raw_content="Acme Corp is a leading provider of...",
    )
    assert profile.consulting_case_id == source.consulting_case_id == CASE_ID
    assert source.collection_successful is True


def test_extracted_company_information_defaults_are_empty_not_none():
    info = ExtractedCompanyInformation(consulting_case_id=CASE_ID)
    assert info.products_and_services == []
    assert info.pricing_information == []


def test_market_research_holds_competitors():
    research = MarketResearch(
        consulting_case_id=CASE_ID,
        industry_overview="B2B SaaS project management tools",
        competitors=[CompetitorProfile(name="Rival Inc", website_url="https://rival.example.com")],
        market_trends=["Shift toward AI-assisted workflows"],
    )
    assert research.competitors[0].name == "Rival Inc"


def test_business_diagnosis_marketing_is_recommended_helper():
    diagnosis = BusinessDiagnosis(
        consulting_case_id=CASE_ID,
        decision=MarketingNecessityDecision.MARKETING_IS_NOT_THE_PRIMARY_ISSUE,
        primary_bottleneck="Checkout flow has a severe drop-off problem",
        reasoning_summary="Traffic and awareness are healthy; conversion at checkout is not.",
        supporting_findings=[build_sample_finding()],
        confidence=ConfidenceLevel.HIGH,
    )
    assert diagnosis.marketing_is_recommended() is False


def test_marketing_strategy_requires_override_warning_when_overridden():
    with pytest.raises(ValidationError):
        MarketingStrategy(
            consulting_case_id=CASE_ID,
            generated_because=StrategyGenerationReason.USER_REQUESTED_STRATEGY_DESPITE_DIAGNOSIS,
            executive_summary="Strategy generated on user request.",
            # override_warning_message intentionally omitted -> should fail
        )


def test_marketing_strategy_succeeds_with_override_warning_present():
    strategy = MarketingStrategy(
        consulting_case_id=CASE_ID,
        generated_because=StrategyGenerationReason.USER_REQUESTED_STRATEGY_DESPITE_DIAGNOSIS,
        executive_summary="Strategy generated on user request.",
        override_warning_message=(
            "The diagnosis indicates that marketing is not the primary business "
            "issue and this strategy is generated only because the user "
            "explicitly requested it."
        ),
        key_initiatives=[
            StrategyInitiative(
                title="Improve retargeting",
                description="Launch a retargeting campaign for cart abandoners.",
            )
        ],
    )
    assert strategy.override_warning_message is not None


def test_generated_report_diagnosis_only_rejects_attached_strategy():
    diagnosis = BusinessDiagnosis(
        consulting_case_id=CASE_ID,
        decision=MarketingNecessityDecision.MARKETING_IS_NOT_THE_PRIMARY_ISSUE,
        primary_bottleneck="Checkout flow has a severe drop-off problem",
        reasoning_summary="Traffic is healthy; conversion is not.",
    )
    strategy = MarketingStrategy(
        consulting_case_id=CASE_ID,
        generated_because=StrategyGenerationReason.USER_REQUESTED_STRATEGY_DESPITE_DIAGNOSIS,
        executive_summary="Strategy generated on user request.",
        override_warning_message="Generated despite diagnosis, per user request.",
    )
    with pytest.raises(ValidationError):
        GeneratedReport(
            consulting_case_id=CASE_ID,
            report_type=ReportType.DIAGNOSIS_ONLY,
            diagnosis=diagnosis,
            strategy=strategy,  # inconsistent with DIAGNOSIS_ONLY -> should fail
        )


def test_generated_report_diagnosis_and_strategy_requires_strategy():
    diagnosis = BusinessDiagnosis(
        consulting_case_id=CASE_ID,
        decision=MarketingNecessityDecision.MARKETING_IS_THE_PRIMARY_ISSUE,
        primary_bottleneck="Low brand awareness in target segment",
        reasoning_summary="Product and pricing are competitive; awareness is the gap.",
    )
    with pytest.raises(ValidationError):
        GeneratedReport(
            consulting_case_id=CASE_ID,
            report_type=ReportType.DIAGNOSIS_AND_STRATEGY,
            diagnosis=diagnosis,
            strategy=None,  # missing -> should fail
        )
