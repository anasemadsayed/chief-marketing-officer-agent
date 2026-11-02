"""
Consulting Pipeline (Brick 11, Part 1).

The "main flow wiring" that ties every previous brick together into the
actual product flow described in the spec:

    User Input -> Create Consulting Case -> Collect Company Information
    -> Perform Market Research -> Extract Useful Business Information
    -> Run Orchestrator -> Business Diagnosis -> Is Marketing Needed?
       YES -> Generate Marketing Strategy -> Generate PowerPoint -> Report
       NO  -> Generate Diagnosis Report -> (user may request the
              strategy anyway later, via
              generate_marketing_strategy_report_for_existing_case)

This module contains no HTTP concerns at all — it's plain Python
functions over the services/orchestrator/storage packages, fully
testable without a web framework. Part 2 (api/main.py) wraps these two
entry points in an HTTP API.

Like the orchestrator, this module does not paper over failures: any
exception raised by a required step (missing input, diagnosis failure,
strategy failure) is allowed to propagate, but not before the
consulting case is marked FAILED with the error recorded as
failure_reason, so nothing fails silently or half-finished.
"""

from __future__ import annotations

from typing import Optional

from domain import CollectedSource, ConsultingCase, ConsultingCaseStatus, GeneratedReport
from orchestrator import (
    analyze_company_business_case_for_consulting_case,
    generate_business_diagnosis_report_for_consulting_case,
    generate_marketing_strategy_report_despite_diagnosis_for_consulting_case,
)
from services import (
    collect_pdf_content_for_consulting_case,
    collect_social_media_profiles_for_consulting_case,
    collect_website_content_for_consulting_case,
    create_business_consulting_presentation_for_consulting_case,
    extract_useful_business_information_for_consulting_case,
    perform_market_and_competitor_research_for_consulting_case,
)
from storage import (
    create_consulting_case,
    list_collected_sources_for_case,
    update_consulting_case_status,
)


class ConsultingPipelineError(RuntimeError):
    """
    Raised when the pipeline cannot proceed for a reason that isn't
    already covered by a more specific error from the orchestrator
    (e.g. no input source was provided at all).
    """


def run_consulting_case_analysis_pipeline(
    company_name: str,
    website_url: Optional[str] = None,
    pdf_file_path: Optional[str] = None,
    linkedin_url: Optional[str] = None,
    facebook_url: Optional[str] = None,
    instagram_url: Optional[str] = None,
    additional_links: Optional[list[str]] = None,
) -> GeneratedReport:
    """
    Run the full V1 consulting flow end-to-end for a brand-new case.

    Creates the case, collects every provided input source, performs
    market research, extracts clean business information, diagnoses the
    business case, and generates the appropriate report — diagnosis-only,
    or diagnosis-and-strategy if marketing was recommended — including
    its PowerPoint deliverable.

    Does NOT handle the "generate a strategy anyway" override for a "no"
    diagnosis; see generate_marketing_strategy_report_for_existing_case
    for that, called separately once the user has seen this report.

    Raises ConsultingPipelineError if no input source was provided.
    Raises OrchestratorError if diagnosis or strategy generation fails.
    In either case the consulting case is marked FAILED with the error
    recorded as failure_reason before the exception propagates.
    """
    consulting_case = create_consulting_case(
        company_name=company_name,
        website_url=website_url,
        pdf_file_path=pdf_file_path,
        linkedin_url=linkedin_url,
        facebook_url=facebook_url,
        instagram_url=instagram_url,
        additional_links=additional_links or [],
    )

    try:
        if not consulting_case.has_at_least_one_input_source():
            raise ConsultingPipelineError(
                f"Cannot analyze case '{consulting_case.id}': no input source (website, "
                "PDF, LinkedIn, Facebook, Instagram, or additional links) was provided."
            )

        update_consulting_case_status(consulting_case.id, ConsultingCaseStatus.COLLECTING_INFORMATION)
        collect_company_information_from_all_sources(consulting_case)

        update_consulting_case_status(consulting_case.id, ConsultingCaseStatus.PERFORMING_MARKET_RESEARCH)
        collected_sources = list_collected_sources_for_case(consulting_case.id)
        perform_market_and_competitor_research_for_consulting_case(
            consulting_case_id=consulting_case.id,
            company_name=company_name,
            collected_sources=collected_sources,
        )

        update_consulting_case_status(consulting_case.id, ConsultingCaseStatus.EXTRACTING_INFORMATION)
        extract_useful_business_information_for_consulting_case(
            consulting_case_id=consulting_case.id, company_name=company_name
        )

        update_consulting_case_status(consulting_case.id, ConsultingCaseStatus.DIAGNOSING_BUSINESS_CASE)
        diagnosis = analyze_company_business_case_for_consulting_case(
            consulting_case_id=consulting_case.id, company_name=company_name
        )

        if diagnosis.marketing_is_recommended():
            update_consulting_case_status(consulting_case.id, ConsultingCaseStatus.GENERATING_STRATEGY)

        report = generate_business_diagnosis_report_for_consulting_case(
            consulting_case_id=consulting_case.id, company_name=company_name
        )

        report = create_business_consulting_presentation_for_consulting_case(
            consulting_case_id=consulting_case.id, company_name=company_name
        )

        update_consulting_case_status(consulting_case.id, ConsultingCaseStatus.COMPLETED)
        return report

    except Exception as error:
        update_consulting_case_status(
            consulting_case.id, ConsultingCaseStatus.FAILED, failure_reason=str(error)
        )
        raise


def generate_marketing_strategy_report_for_existing_case(
    consulting_case_id: str,
    company_name: str,
) -> GeneratedReport:
    """
    Handle the explicit "generate a marketing strategy anyway" action for
    a case that already has a diagnosis-only report: generates the
    override strategy (with its required disclaimer), regenerates the
    PowerPoint deliverable (the earlier diagnosis-only deck is now out
    of date), and returns the updated report.

    Raises OrchestratorError if the diagnosis actually already
    recommended marketing (nothing to override) or if strategy
    generation fails. The case is marked FAILED with the error recorded
    before the exception propagates, matching
    run_consulting_case_analysis_pipeline's behavior.
    """
    try:
        update_consulting_case_status(consulting_case_id, ConsultingCaseStatus.GENERATING_STRATEGY)

        generate_marketing_strategy_report_despite_diagnosis_for_consulting_case(
            consulting_case_id=consulting_case_id, company_name=company_name
        )

        report = create_business_consulting_presentation_for_consulting_case(
            consulting_case_id=consulting_case_id, company_name=company_name
        )

        update_consulting_case_status(consulting_case_id, ConsultingCaseStatus.COMPLETED)
        return report

    except Exception as error:
        update_consulting_case_status(
            consulting_case_id, ConsultingCaseStatus.FAILED, failure_reason=str(error)
        )
        raise


def collect_company_information_from_all_sources(consulting_case: ConsultingCase) -> list[CollectedSource]:
    """
    Run every applicable collector for this case's provided input
    sources and return everything collected.

    Each collector (Bricks 4-5) already persists its own results and
    degrades gracefully on failure — this function simply calls
    whichever collectors are relevant to what the user actually
    provided and aggregates their results. Additional links are
    collected as single pages (max_pages=1) via the website collector,
    rather than crawled as if each were its own homepage.
    """
    collected_sources: list[CollectedSource] = []

    if consulting_case.website_url:
        collected_sources.extend(
            collect_website_content_for_consulting_case(
                consulting_case_id=consulting_case.id,
                website_url=str(consulting_case.website_url),
            )
        )

    if consulting_case.pdf_file_path:
        collected_sources.append(
            collect_pdf_content_for_consulting_case(
                consulting_case_id=consulting_case.id,
                pdf_file_path=consulting_case.pdf_file_path,
            )
        )

    collected_sources.extend(
        collect_social_media_profiles_for_consulting_case(
            consulting_case_id=consulting_case.id,
            linkedin_url=str(consulting_case.linkedin_url) if consulting_case.linkedin_url else None,
            facebook_url=str(consulting_case.facebook_url) if consulting_case.facebook_url else None,
            instagram_url=str(consulting_case.instagram_url) if consulting_case.instagram_url else None,
        )
    )

    for additional_link in consulting_case.additional_links:
        collected_sources.extend(
            collect_website_content_for_consulting_case(
                consulting_case_id=consulting_case.id,
                website_url=str(additional_link),
                max_pages=1,
            )
        )

    return collected_sources
