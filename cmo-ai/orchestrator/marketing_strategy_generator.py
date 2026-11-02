"""
Orchestrator: Marketing Strategy Generation (Brick 9, Part 1).

Wraps the main reasoning LLM to turn a completed BusinessDiagnosis, the
cleaned company information, and the market research into a concrete,
evidence-based marketing strategy.

Used in exactly two situations, distinguished by `generated_because`:
1. DIAGNOSIS_RECOMMENDED_MARKETING — the diagnosis concluded marketing
   IS the primary issue.
2. USER_REQUESTED_STRATEGY_DESPITE_DIAGNOSIS — the diagnosis said
   marketing is NOT the primary issue, but the user explicitly asked
   for a strategy anyway. In this case the required disclaimer is
   attached automatically; the caller never has to construct it.

Like the diagnosis generator (Brick 8), this module does NOT degrade
gracefully on failure — an invented strategy not actually grounded in
the evidence would be worse than no strategy at all. Any failure raises
OrchestratorError and saves nothing.

The decision logic for WHICH of these two situations applies (i.e. the
"is marketing needed? yes/no/generate anyway" branching and the final
report composition) is Brick 9, Part 2 — not implemented here.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from config.settings import settings
from domain import (
    BusinessDiagnosis,
    ExtractedCompanyInformation,
    Finding,
    MarketResearch,
    MarketingStrategy,
    StrategyGenerationReason,
    StrategyInitiative,
)
from orchestrator.context_builders import (
    build_diagnosis_context,
    build_extracted_information_context,
    build_market_research_context,
)
from orchestrator.errors import OrchestratorError
from orchestrator.main_llm_client import MainLlmClientError, generate_json_response_from_main_llm
from storage.business_diagnosis_repository import get_business_diagnosis_by_case_id
from storage.extracted_company_information_repository import get_extracted_information_by_case_id
from storage.market_research_repository import get_market_research_by_case_id
from storage.marketing_strategy_repository import save_marketing_strategy

logger = logging.getLogger(__name__)

_MARKETING_STRATEGY_PROMPT_TEMPLATE = """\
You are a senior marketing strategist. A business diagnosis for this \
company is provided below. Your job is to produce a concrete, \
evidence-based marketing strategy grounded in the company information, \
market research, and diagnosis given — not a generic, one-size-fits-all \
plan.

Return ONLY a JSON object (no markdown formatting, no commentary) with \
exactly this shape:

{{
  "executive_summary": "2-4 sentence summary of the overall strategy",
  "strategic_objectives": ["objective one", "objective two"],
  "recommended_channels": ["channel one", "channel two"],
  "key_initiatives": [
    {{
      "title": "short initiative name",
      "description": "what this initiative involves, concretely",
      "expected_impact": "what this is expected to achieve, and why",
      "supporting_evidence": ["evidence point one", "evidence point two"]
    }}
  ],
  "supporting_findings": [
    {{
      "description": "a specific observation supporting the strategy",
      "evidence": "the concrete evidence for it, drawn from the data below",
      "source_reference": "where this evidence came from, e.g. 'extracted_information:target_audience_signals'",
      "confidence": "low", "medium", or "high"
    }}
  ]
}}

Rules:
- Every initiative must be grounded in the evidence below — the company's \
actual products, audience, pricing, competitors, or the diagnosis itself. \
Do not propose tactics that ignore the specific evidence provided.
- Include 3-6 concrete key_initiatives.
- Recommend channels that make sense given the target audience and \
industry described below, not a generic list of "social media, email, SEO".
- Build on the diagnosis rather than repeating it verbatim.
- Keep list items concise.

Company name: {company_name}

--- Business Diagnosis ---
{diagnosis_block}

--- Company Information (cleaned) ---
{extracted_information_block}

--- Market Research ---
{market_research_block}"""


def generate_marketing_strategy(
    consulting_case_id: str,
    company_name: str,
    diagnosis: BusinessDiagnosis,
    extracted_information: ExtractedCompanyInformation,
    market_research: MarketResearch,
    generated_because: StrategyGenerationReason = StrategyGenerationReason.DIAGNOSIS_RECOMMENDED_MARKETING,
) -> MarketingStrategy:
    """
    Generate an evidence-based marketing strategy and persist it.

    Raises OrchestratorError (saving nothing) if:
    - generated_because=DIAGNOSIS_RECOMMENDED_MARKETING but the diagnosis
      did not actually recommend marketing (a caller bug — use
      USER_REQUESTED_STRATEGY_DESPITE_DIAGNOSIS for the explicit
      override path instead),
    - generated_because=USER_REQUESTED_STRATEGY_DESPITE_DIAGNOSIS but the
      diagnosis actually DID recommend marketing (attaching the override
      disclaimer here would be false — there is nothing to override), or
    - the main LLM call fails or returns something unusable.
    """
    if (
        generated_because == StrategyGenerationReason.DIAGNOSIS_RECOMMENDED_MARKETING
        and not diagnosis.marketing_is_recommended()
    ):
        raise OrchestratorError(
            "generate_marketing_strategy was called with generated_because="
            "DIAGNOSIS_RECOMMENDED_MARKETING but the diagnosis did not recommend "
            "marketing. Use generated_because=USER_REQUESTED_STRATEGY_DESPITE_DIAGNOSIS "
            "for the explicit override path instead."
        )

    if (
        generated_because == StrategyGenerationReason.USER_REQUESTED_STRATEGY_DESPITE_DIAGNOSIS
        and diagnosis.marketing_is_recommended()
    ):
        raise OrchestratorError(
            "generate_marketing_strategy was called with generated_because="
            "USER_REQUESTED_STRATEGY_DESPITE_DIAGNOSIS but the diagnosis already "
            "recommended marketing. Use generated_because=DIAGNOSIS_RECOMMENDED_MARKETING "
            "instead — the override path is only for overriding a 'no' diagnosis, and "
            "attaching the override disclaimer here would be misleading."
        )

    diagnosis_block = build_diagnosis_context(diagnosis)
    extracted_information_block = build_extracted_information_context(extracted_information)
    market_research_block = build_market_research_context(market_research)

    prompt = _MARKETING_STRATEGY_PROMPT_TEMPLATE.format(
        company_name=company_name,
        diagnosis_block=diagnosis_block or "(no diagnosis details available)",
        extracted_information_block=extracted_information_block or "(no company information was collected)",
        market_research_block=market_research_block or "(no market research was collected)",
    )

    try:
        response_data = generate_json_response_from_main_llm(
            prompt,
            temperature=settings.strategy_llm_temperature,
            max_output_tokens=settings.strategy_llm_max_output_tokens,
        )
        strategy = _parse_strategy_response(consulting_case_id, generated_because, diagnosis, response_data)
    except (MainLlmClientError, ValidationError, TypeError, ValueError, KeyError) as error:
        logger.error("Marketing strategy generation failed for case=%s: %s", consulting_case_id, error)
        raise OrchestratorError(f"Could not generate a marketing strategy: {error}") from error

    save_marketing_strategy(strategy)
    logger.info(
        "Marketing strategy generated and saved for case=%s (reason=%s)",
        consulting_case_id, generated_because.value,
    )
    return strategy


def generate_marketing_strategy_for_consulting_case(
    consulting_case_id: str,
    company_name: str,
    generated_because: StrategyGenerationReason = StrategyGenerationReason.DIAGNOSIS_RECOMMENDED_MARKETING,
) -> MarketingStrategy:
    """
    Convenience entry point for the main pipeline: pulls the diagnosis,
    extracted information, and market research straight from storage.

    Raises OrchestratorError if any of the three required inputs is
    missing, or if strategy generation itself fails.
    """
    diagnosis = get_business_diagnosis_by_case_id(consulting_case_id)
    if diagnosis is None:
        raise OrchestratorError(
            f"Cannot generate a strategy for case '{consulting_case_id}': no diagnosis "
            "found. Run the diagnosis step first."
        )

    extracted_information = get_extracted_information_by_case_id(consulting_case_id)
    if extracted_information is None:
        raise OrchestratorError(
            f"Cannot generate a strategy for case '{consulting_case_id}': no extracted "
            "company information found. Run the Information Extraction Service first."
        )

    market_research = get_market_research_by_case_id(consulting_case_id)
    if market_research is None:
        raise OrchestratorError(
            f"Cannot generate a strategy for case '{consulting_case_id}': no market "
            "research found. Run the Market Research Service first."
        )

    return generate_marketing_strategy(
        consulting_case_id=consulting_case_id,
        company_name=company_name,
        diagnosis=diagnosis,
        extracted_information=extracted_information,
        market_research=market_research,
        generated_because=generated_because,
    )


def _parse_strategy_response(
    consulting_case_id: str,
    generated_because: StrategyGenerationReason,
    diagnosis: BusinessDiagnosis,
    data: dict,
) -> MarketingStrategy:
    """Map the LLM's raw JSON dict onto a validated MarketingStrategy domain object."""
    initiatives_raw = data.get("key_initiatives") or []
    if not isinstance(initiatives_raw, list):
        raise TypeError(f"Expected 'key_initiatives' to be a list, got {type(initiatives_raw).__name__}")
    key_initiatives = [StrategyInitiative(**item) for item in initiatives_raw]

    findings_raw = data.get("supporting_findings") or []
    if not isinstance(findings_raw, list):
        raise TypeError(f"Expected 'supporting_findings' to be a list, got {type(findings_raw).__name__}")
    supporting_findings = [Finding(**finding) for finding in findings_raw]

    override_warning_message = None
    if generated_because == StrategyGenerationReason.USER_REQUESTED_STRATEGY_DESPITE_DIAGNOSIS:
        override_warning_message = _build_override_warning_message(diagnosis)

    return MarketingStrategy(
        consulting_case_id=consulting_case_id,
        generated_because=generated_because,
        executive_summary=data.get("executive_summary", ""),
        strategic_objectives=data.get("strategic_objectives") or [],
        recommended_channels=data.get("recommended_channels") or [],
        key_initiatives=key_initiatives,
        supporting_findings=supporting_findings,
        override_warning_message=override_warning_message,
    )


def _build_override_warning_message(diagnosis: BusinessDiagnosis) -> str:
    """
    The exact disclaimer required by the spec whenever a strategy is
    generated despite a "marketing is not the primary issue" diagnosis.
    Deliberately hardcoded rather than LLM-generated, so its wording is
    always consistent and never accidentally softened or omitted.
    """
    return (
        "The diagnosis indicates that marketing is not the primary business "
        "issue and this strategy is generated only because the user "
        "explicitly requested it. "
        f"Diagnosed primary bottleneck: {diagnosis.primary_bottleneck}"
    )
