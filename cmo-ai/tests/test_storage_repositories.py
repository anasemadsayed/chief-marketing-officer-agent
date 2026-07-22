"""
Tests for the SQLite storage layer (Brick 3).

Each test uses the `isolated_test_database` fixture (see conftest.py) so
nothing here ever touches a real ./data/cmoai.db file. Covers: schema
creation, id uniqueness, and a full save -> get round trip for every one
of the 8 tables, proving domain models survive the trip unchanged.
"""

from __future__ import annotations

from domain import (
    BusinessDiagnosis,
    CollectedSource,
    CompanyProfile,
    CompetitorProfile,
    ConfidenceLevel,
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
from storage.business_diagnosis_repository import (
    get_business_diagnosis_by_case_id,
    save_business_diagnosis,
)
from storage.collected_source_repository import (
    create_and_save_collected_source,
    list_collected_sources_for_case,
)
from storage.company_profile_repository import (
    get_company_profile_by_case_id,
    save_company_profile,
)
from storage.consulting_case_repository import (
    create_consulting_case,
    get_consulting_case_by_id,
    update_consulting_case_status,
)
from storage.extracted_company_information_repository import (
    get_extracted_information_by_case_id,
    save_extracted_information,
)
from storage.generated_report_repository import (
    get_generated_report_by_case_id,
    save_generated_report,
)
from storage.id_generator import generate_unique_consulting_case_id
from storage.market_research_repository import (
    get_market_research_by_case_id,
    save_market_research,
)
from storage.marketing_strategy_repository import (
    get_marketing_strategy_by_case_id,
    save_marketing_strategy,
)


def test_generated_case_ids_are_unique_even_for_same_company_name():
    first_id = generate_unique_consulting_case_id("Acme Corp")
    second_id = generate_unique_consulting_case_id("Acme Corp")
    assert first_id != second_id
    assert first_id.startswith("acme-corp-")


def test_create_and_fetch_consulting_case(isolated_test_database):
    case = create_consulting_case(
        company_name="Acme Corp",
        website_url="https://acme.example.com",
        additional_links=["https://acme.example.com/blog"],
    )
    fetched = get_consulting_case_by_id(case.id)

    assert fetched is not None
    assert fetched.id == case.id
    assert fetched.company_name == "Acme Corp"
    assert fetched.status == ConsultingCaseStatus.CREATED
    assert str(fetched.website_url) == "https://acme.example.com/"
    assert len(fetched.additional_links) == 1


def test_update_consulting_case_status(isolated_test_database):
    case = create_consulting_case(company_name="Acme Corp")
    update_consulting_case_status(case.id, ConsultingCaseStatus.FAILED, failure_reason="No sources reachable")

    fetched = get_consulting_case_by_id(case.id)
    assert fetched.status == ConsultingCaseStatus.FAILED
    assert fetched.failure_reason == "No sources reachable"


def test_company_profile_save_and_get(isolated_test_database):
    case = create_consulting_case(company_name="Acme Corp")
    save_company_profile(
        CompanyProfile(
            consulting_case_id=case.id,
            company_name="Acme Corp",
            industry="B2B SaaS",
            website_url="https://acme.example.com",
        )
    )
    fetched = get_company_profile_by_case_id(case.id)
    assert fetched.industry == "B2B SaaS"


def test_collected_sources_multiple_rows_per_case(isolated_test_database):
    case = create_consulting_case(company_name="Acme Corp")
    create_and_save_collected_source(
        consulting_case_id=case.id,
        source_type=InformationSourceType.COMPANY_WEBSITE,
        source_url_or_path="https://acme.example.com/about",
        raw_content="About Acme...",
    )
    create_and_save_collected_source(
        consulting_case_id=case.id,
        source_type=InformationSourceType.LINKEDIN_PROFILE,
        source_url_or_path="https://linkedin.com/company/acme",
        raw_content="Acme on LinkedIn...",
    )
    sources = list_collected_sources_for_case(case.id)
    assert len(sources) == 2
    assert {s.source_type for s in sources} == {
        InformationSourceType.COMPANY_WEBSITE,
        InformationSourceType.LINKEDIN_PROFILE,
    }


def test_extracted_company_information_save_and_get(isolated_test_database):
    case = create_consulting_case(company_name="Acme Corp")
    save_extracted_information(
        ExtractedCompanyInformation(
            consulting_case_id=case.id,
            company_description_summary="Acme builds project management software.",
            products_and_services=["Project tracker", "Time billing"],
            pricing_information=["$29/user/month"],
        )
    )
    fetched = get_extracted_information_by_case_id(case.id)
    assert fetched.products_and_services == ["Project tracker", "Time billing"]
    assert fetched.pricing_information == ["$29/user/month"]


def test_market_research_save_and_get_with_nested_competitors(isolated_test_database):
    case = create_consulting_case(company_name="Acme Corp")
    save_market_research(
        MarketResearch(
            consulting_case_id=case.id,
            industry_overview="Project management SaaS",
            competitors=[
                CompetitorProfile(name="Rival Inc", website_url="https://rival.example.com"),
                CompetitorProfile(name="Other Co"),
            ],
            market_trends=["AI-assisted planning"],
        )
    )
    fetched = get_market_research_by_case_id(case.id)
    assert len(fetched.competitors) == 2
    assert fetched.competitors[0].name == "Rival Inc"
    assert fetched.market_trends == ["AI-assisted planning"]


def test_business_diagnosis_save_and_get_with_findings(isolated_test_database):
    case = create_consulting_case(company_name="Acme Corp")
    save_business_diagnosis(
        BusinessDiagnosis(
            consulting_case_id=case.id,
            decision=MarketingNecessityDecision.MARKETING_IS_NOT_THE_PRIMARY_ISSUE,
            primary_bottleneck="Checkout flow has a severe drop-off problem",
            reasoning_summary="Traffic is healthy; conversion at checkout is not.",
            supporting_findings=[
                Finding(
                    description="68% cart abandonment",
                    evidence="Analytics report, last 30 days",
                    source_reference="uploaded_pdf:analytics_report",
                    confidence=ConfidenceLevel.HIGH,
                )
            ],
            confidence=ConfidenceLevel.HIGH,
        )
    )
    fetched = get_business_diagnosis_by_case_id(case.id)
    assert fetched.decision == MarketingNecessityDecision.MARKETING_IS_NOT_THE_PRIMARY_ISSUE
    assert len(fetched.supporting_findings) == 1
    assert fetched.supporting_findings[0].description == "68% cart abandonment"


def test_marketing_strategy_save_and_get_with_initiatives(isolated_test_database):
    case = create_consulting_case(company_name="Acme Corp")
    save_marketing_strategy(
        MarketingStrategy(
            consulting_case_id=case.id,
            generated_because=StrategyGenerationReason.DIAGNOSIS_RECOMMENDED_MARKETING,
            executive_summary="Focus on outbound + content in Q1.",
            key_initiatives=[
                StrategyInitiative(
                    title="Launch LinkedIn outbound",
                    description="Target VP-level buyers in mid-market SaaS.",
                )
            ],
        )
    )
    fetched = get_marketing_strategy_by_case_id(case.id)
    assert fetched.key_initiatives[0].title == "Launch LinkedIn outbound"
    assert fetched.override_warning_message is None


def test_generated_report_diagnosis_only_round_trip(isolated_test_database):
    case = create_consulting_case(company_name="Acme Corp")
    diagnosis = BusinessDiagnosis(
        consulting_case_id=case.id,
        decision=MarketingNecessityDecision.MARKETING_IS_NOT_THE_PRIMARY_ISSUE,
        primary_bottleneck="Checkout flow has a severe drop-off problem",
        reasoning_summary="Traffic is healthy; conversion is not.",
    )
    save_business_diagnosis(diagnosis)
    save_generated_report(
        GeneratedReport(
            consulting_case_id=case.id,
            report_type=ReportType.DIAGNOSIS_ONLY,
            diagnosis=diagnosis,
        )
    )

    fetched = get_generated_report_by_case_id(case.id)
    assert fetched.report_type == ReportType.DIAGNOSIS_ONLY
    assert fetched.strategy is None
    assert fetched.diagnosis.primary_bottleneck == "Checkout flow has a severe drop-off problem"


def test_generated_report_diagnosis_and_strategy_round_trip(isolated_test_database):
    case = create_consulting_case(company_name="Acme Corp")
    diagnosis = BusinessDiagnosis(
        consulting_case_id=case.id,
        decision=MarketingNecessityDecision.MARKETING_IS_THE_PRIMARY_ISSUE,
        primary_bottleneck="Low brand awareness in target segment",
        reasoning_summary="Product and pricing are competitive; awareness is the gap.",
    )
    strategy = MarketingStrategy(
        consulting_case_id=case.id,
        generated_because=StrategyGenerationReason.DIAGNOSIS_RECOMMENDED_MARKETING,
        executive_summary="Build category awareness via content + partnerships.",
    )
    save_business_diagnosis(diagnosis)
    save_marketing_strategy(strategy)
    save_generated_report(
        GeneratedReport(
            consulting_case_id=case.id,
            report_type=ReportType.DIAGNOSIS_AND_STRATEGY,
            diagnosis=diagnosis,
            strategy=strategy,
            powerpoint_file_path="/mnt/user-data/outputs/acme-report.pptx",
        )
    )

    fetched = get_generated_report_by_case_id(case.id)
    assert fetched.strategy is not None
    assert fetched.strategy.executive_summary.startswith("Build category awareness")
    assert fetched.powerpoint_file_path == "/mnt/user-data/outputs/acme-report.pptx"
