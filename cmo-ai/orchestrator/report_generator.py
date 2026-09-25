"""
Orchestrator: Report Generation & Decision Wiring (Brick 9, Part 2).

This is where the product's central decision actually gets acted on:
given a completed BusinessDiagnosis, decide whether to auto-generate a
marketing strategy or return a diagnosis-only report — and provide the
explicit "generate a strategy anyway" override path for when the user
disagrees with a "no" diagnosis.

Three entry points:
1. generate_business_diagnosis_report(...) — the automatic post-diagnosis
   flow. If the diagnosis recommends marketing, a strategy is generated
   automatically and the report includes both. If not, a diagnosis-only
   report is returned and NO strategy is generated — per the spec, the
   user must explicitly ask for one.
2. generate_marketing_strategy_report_despite_diagnosis(...) — the
   explicit override the user can invoke after seeing a diagnosis-only
   report. Always produces a strategy carrying the required disclaimer
   (enforced by generate_marketing_strategy's own guard).
3. The "_for_consulting_case" variants of both, pulling their inputs
   from storage.

Like the rest of the orchestrator, this module does not fabricate a
result on failure: any error generating a strategy propagates as
OrchestratorError, and no GeneratedReport is ever saved for a case where
that error occurred.
"""

from __future__ import annotations

import logging
from typing import Optional

from domain import (
    BusinessDiagnosis,
    ExtractedCompanyInformation,
    GeneratedReport,
    MarketResearch,
    ReportType,
    StrategyGenerationReason,
)
from orchestrator.errors import OrchestratorError
from orchestrator.marketing_strategy_generator import generate_marketing_strategy
from storage.business_diagnosis_repository import (
    get_business_diagnosis_by_case_id,
    save_business_diagnosis,
)
from storage.extracted_company_information_repository import get_extracted_information_by_case_id
from storage.generated_report_repository import save_generated_report
from storage.market_research_repository import get_market_research_by_case_id

logger = logging.getLogger(__name__)


def generate_business_diagnosis_report(
    consulting_case_id: str,
    company_name: str,
    diagnosis: BusinessDiagnosis,
    extracted_information: Optional[ExtractedCompanyInformation] = None,
    market_research: Optional[MarketResearch] = None,
) -> GeneratedReport:
    """
    Produce the report for a consulting case based on its diagnosis.

    If the diagnosis recommends marketing, `extracted_information` and
    `market_research` are required (they're needed to generate the
    strategy) and a DIAGNOSIS_AND_STRATEGY report is produced. If the
    diagnosis does NOT recommend marketing, neither is needed and a
    DIAGNOSIS_ONLY report is produced — no strategy is generated
    automatically, per the spec.

    The diagnosis is (re-)persisted defensively before the report is
    saved: GeneratedReport composition requires the diagnosis row to
    already exist (see generated_report_repository's data-integrity
    check), and callers may reasonably pass a diagnosis object they
    already have in hand rather than one freshly re-fetched from
    storage. save_business_diagnosis is idempotent (INSERT OR REPLACE),
    so this is a no-op if it was already saved.
    """
    save_business_diagnosis(diagnosis)

    if diagnosis.marketing_is_recommended():
        if extracted_information is None or market_research is None:
            raise OrchestratorError(
                f"Cannot generate the marketing strategy for case '{consulting_case_id}': "
                "the diagnosis recommends marketing, but extracted_information and/or "
                "market_research were not provided."
            )

        strategy = generate_marketing_strategy(
            consulting_case_id=consulting_case_id,
            company_name=company_name,
            diagnosis=diagnosis,
            extracted_information=extracted_information,
            market_research=market_research,
            generated_because=StrategyGenerationReason.DIAGNOSIS_RECOMMENDED_MARKETING,
        )
        report = GeneratedReport(
            consulting_case_id=consulting_case_id,
            report_type=ReportType.DIAGNOSIS_AND_STRATEGY,
            diagnosis=diagnosis,
            strategy=strategy,
        )
    else:
        report = GeneratedReport(
            consulting_case_id=consulting_case_id,
            report_type=ReportType.DIAGNOSIS_ONLY,
            diagnosis=diagnosis,
        )

    save_generated_report(report)
    logger.info(
        "Report generated for case=%s type=%s", consulting_case_id, report.report_type.value
    )
    return report


def generate_business_diagnosis_report_for_consulting_case(
    consulting_case_id: str,
    company_name: str,
) -> GeneratedReport:
    """
    Convenience entry point for the main pipeline: pulls the diagnosis
    from storage, and (only if marketing was recommended) the extracted
    information and market research needed to generate a strategy.

    Raises OrchestratorError if the diagnosis is missing, or if marketing
    was recommended but the supporting data needed for strategy
    generation isn't available.
    """
    diagnosis = get_business_diagnosis_by_case_id(consulting_case_id)
    if diagnosis is None:
        raise OrchestratorError(
            f"Cannot generate a report for case '{consulting_case_id}': no diagnosis "
            "found. Run the diagnosis step first."
        )

    if not diagnosis.marketing_is_recommended():
        return generate_business_diagnosis_report(consulting_case_id, company_name, diagnosis)

    extracted_information = get_extracted_information_by_case_id(consulting_case_id)
    market_research = get_market_research_by_case_id(consulting_case_id)
    if extracted_information is None or market_research is None:
        raise OrchestratorError(
            f"Cannot generate the marketing strategy for case '{consulting_case_id}': "
            "extracted company information and/or market research is missing."
        )

    return generate_business_diagnosis_report(
        consulting_case_id, company_name, diagnosis, extracted_information, market_research
    )


def generate_marketing_strategy_report_despite_diagnosis(
    consulting_case_id: str,
    company_name: str,
    diagnosis: BusinessDiagnosis,
    extracted_information: ExtractedCompanyInformation,
    market_research: MarketResearch,
) -> GeneratedReport:
    """
    The explicit "generate a marketing strategy anyway" path: the user
    has seen a diagnosis-only report saying marketing is NOT the primary
    issue, and has chosen to request a strategy regardless.

    Always produces a DIAGNOSIS_AND_STRATEGY report carrying the
    required override disclaimer (attached automatically by
    generate_marketing_strategy). Raises OrchestratorError if the
    diagnosis actually recommended marketing — there is nothing to
    override in that case (see generate_marketing_strategy's guard).

    Like generate_business_diagnosis_report, the diagnosis is
    (re-)persisted defensively before the report is saved.
    """
    save_business_diagnosis(diagnosis)

    strategy = generate_marketing_strategy(
        consulting_case_id=consulting_case_id,
        company_name=company_name,
        diagnosis=diagnosis,
        extracted_information=extracted_information,
        market_research=market_research,
        generated_because=StrategyGenerationReason.USER_REQUESTED_STRATEGY_DESPITE_DIAGNOSIS,
    )
    report = GeneratedReport(
        consulting_case_id=consulting_case_id,
        report_type=ReportType.DIAGNOSIS_AND_STRATEGY,
        diagnosis=diagnosis,
        strategy=strategy,
    )

    save_generated_report(report)
    logger.info("Override strategy report generated for case=%s", consulting_case_id)
    return report


def generate_marketing_strategy_report_despite_diagnosis_for_consulting_case(
    consulting_case_id: str,
    company_name: str,
) -> GeneratedReport:
    """
    Convenience entry point for the main pipeline's override path: pulls
    the diagnosis, extracted information, and market research from
    storage. All three are required regardless of the diagnosis
    decision, since strategy generation always needs them.
    """
    diagnosis = get_business_diagnosis_by_case_id(consulting_case_id)
    if diagnosis is None:
        raise OrchestratorError(
            f"Cannot override for case '{consulting_case_id}': no diagnosis found."
        )

    extracted_information = get_extracted_information_by_case_id(consulting_case_id)
    if extracted_information is None:
        raise OrchestratorError(
            f"Cannot override for case '{consulting_case_id}': no extracted company "
            "information found."
        )

    market_research = get_market_research_by_case_id(consulting_case_id)
    if market_research is None:
        raise OrchestratorError(
            f"Cannot override for case '{consulting_case_id}': no market research found."
        )

    return generate_marketing_strategy_report_despite_diagnosis(
        consulting_case_id, company_name, diagnosis, extracted_information, market_research
    )
