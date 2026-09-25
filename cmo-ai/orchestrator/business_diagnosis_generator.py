"""
Orchestrator: Business Diagnosis.

The first "intelligent" brick. Wraps the main reasoning LLM to answer the
central question of the whole product: is marketing actually this
company's primary problem, or does the real bottleneck lie elsewhere
(pricing, product-market fit, website conversion, sales process, weak
differentiation, market saturation, etc.)?

Unlike the non-reasoning services (Bricks 4-7), this module does NOT
degrade gracefully on failure. A fabricated diagnosis would be actively
misleading — worse than no diagnosis at all. If the LLM call fails or
returns something unusable, `analyze_company_business_case` raises
OrchestratorError and saves nothing. Callers (Brick 11's pipeline
wiring) are expected to catch this and mark the ConsultingCase as
FAILED with the error as `failure_reason`.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from config.settings import settings
from domain import BusinessDiagnosis, ExtractedCompanyInformation, Finding, MarketResearch
from orchestrator.context_builders import build_extracted_information_context, build_market_research_context
from orchestrator.errors import OrchestratorError
from orchestrator.main_llm_client import MainLlmClientError, generate_json_response_from_main_llm
from storage.business_diagnosis_repository import save_business_diagnosis
from storage.extracted_company_information_repository import get_extracted_information_by_case_id
from storage.market_research_repository import get_market_research_by_case_id

logger = logging.getLogger(__name__)

_DIAGNOSIS_PROMPT_TEMPLATE = """\
You are a senior business consultant performing a root-cause diagnosis \
for a company that is considering a marketing strategy. Your job is to \
determine whether marketing is genuinely this company's primary problem, \
or whether the real bottleneck lies elsewhere — for example pricing \
misalignment, weak product-market fit, poor website/conversion \
experience, an ineffective sales process, unclear differentiation, \
unclear target audience, or a saturated/hyper-competitive market.

Base your diagnosis ONLY on the evidence provided below. Do not assume \
marketing is the answer by default — many companies that believe they \
need more marketing actually have a different underlying problem. Be \
honest and rigorous, even if that means concluding marketing is NOT the \
primary issue.

Return ONLY a JSON object (no markdown formatting, no commentary) with \
exactly this shape:

{{
  "decision": "marketing_is_the_primary_issue" or "marketing_is_not_the_primary_issue",
  "primary_bottleneck": "the actual root cause in plain language, one or two sentences",
  "reasoning_summary": "3-6 sentences explaining how you reached this decision, referencing the evidence below",
  "confidence": "low", "medium", or "high",
  "supporting_findings": [
    {{
      "description": "a specific observation supporting the diagnosis",
      "evidence": "the concrete evidence for it, drawn from the data below",
      "source_reference": "where this evidence came from, e.g. 'extracted_information:pricing_information' or 'market_research:competitors'",
      "confidence": "low", "medium", or "high"
    }}
  ]
}}

Rules:
- Every finding must be grounded in the evidence provided below — do not \
invent facts that aren't supported by the data.
- Include at least 2 supporting findings, ideally 3-5.
- The top-level "confidence" reflects your overall confidence in the \
diagnosis, factoring in how much reliable evidence you actually had to \
work with. If the evidence is sparse or unclear, say so honestly with a \
lower confidence rather than overstating certainty.
- "decision" must be exactly one of the two literal strings shown above.

Company name: {company_name}

--- Company Information (cleaned) ---
{extracted_information_block}

--- Market Research ---
{market_research_block}"""


def analyze_company_business_case(
    consulting_case_id: str,
    company_name: str,
    extracted_information: ExtractedCompanyInformation,
    market_research: MarketResearch,
) -> BusinessDiagnosis:
    """
    Run the core root-cause diagnosis for one consulting case and persist
    the result.

    Raises OrchestratorError (and saves nothing) if the main LLM call
    fails or returns a response that can't be turned into a valid
    BusinessDiagnosis. This is intentional: an invented diagnosis would
    mislead the business owner reading the final report, so failure here
    must be visible, not papered over.
    """
    extracted_information_block = build_extracted_information_context(extracted_information)
    market_research_block = build_market_research_context(market_research)

    prompt = _DIAGNOSIS_PROMPT_TEMPLATE.format(
        company_name=company_name,
        extracted_information_block=extracted_information_block or "(no company information was collected)",
        market_research_block=market_research_block or "(no market research was collected)",
    )

    try:
        response_data = generate_json_response_from_main_llm(
            prompt,
            temperature=settings.diagnosis_llm_temperature,
            max_output_tokens=settings.diagnosis_llm_max_output_tokens,
        )
        diagnosis = _parse_diagnosis_response(consulting_case_id, response_data)
    except (MainLlmClientError, ValidationError, TypeError, ValueError, KeyError) as error:
        logger.error("Business diagnosis failed for case=%s: %s", consulting_case_id, error)
        raise OrchestratorError(f"Could not generate a business diagnosis: {error}") from error

    save_business_diagnosis(diagnosis)
    logger.info(
        "Diagnosis complete for case=%s: decision=%s confidence=%s",
        consulting_case_id, diagnosis.decision.value, diagnosis.confidence.value,
    )
    return diagnosis


def analyze_company_business_case_for_consulting_case(
    consulting_case_id: str,
    company_name: str,
) -> BusinessDiagnosis:
    """
    Convenience entry point for the main pipeline: pulls the already-clean
    ExtractedCompanyInformation and MarketResearch straight from storage.

    Raises OrchestratorError if either is missing (diagnosis cannot run
    on data that was never collected/extracted) or if the diagnosis
    itself fails.
    """
    extracted_information = get_extracted_information_by_case_id(consulting_case_id)
    if extracted_information is None:
        raise OrchestratorError(
            f"Cannot diagnose case '{consulting_case_id}': no extracted company "
            "information found. Run the Information Extraction Service first."
        )

    market_research = get_market_research_by_case_id(consulting_case_id)
    if market_research is None:
        raise OrchestratorError(
            f"Cannot diagnose case '{consulting_case_id}': no market research "
            "found. Run the Market Research Service first."
        )

    return analyze_company_business_case(
        consulting_case_id=consulting_case_id,
        company_name=company_name,
        extracted_information=extracted_information,
        market_research=market_research,
    )


def _parse_diagnosis_response(consulting_case_id: str, data: dict) -> BusinessDiagnosis:
    """
    Map the LLM's raw JSON dict onto a validated BusinessDiagnosis domain
    object. Pydantic validation (required, non-empty fields) does most of
    the honesty-enforcement here: a response missing a real bottleneck or
    reasoning summary will fail loudly rather than produce a hollow
    diagnosis.
    """
    findings_raw = data.get("supporting_findings") or []
    if not isinstance(findings_raw, list):
        raise TypeError(f"Expected 'supporting_findings' to be a list, got {type(findings_raw).__name__}")

    supporting_findings = [Finding(**finding) for finding in findings_raw]

    return BusinessDiagnosis(
        consulting_case_id=consulting_case_id,
        decision=data["decision"],
        primary_bottleneck=data.get("primary_bottleneck", ""),
        reasoning_summary=data.get("reasoning_summary", ""),
        supporting_findings=supporting_findings,
        confidence=data.get("confidence", "medium"),
    )
