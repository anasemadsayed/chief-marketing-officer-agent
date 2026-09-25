"""
orchestrator
============

The single intelligent decision-maker in the system.

The orchestrator is the only component allowed to:
- reason about the business,
- perform root-cause diagnosis,
- decide whether marketing is the correct solution,
- generate the marketing strategy,
- generate the final report.

It consumes only clean, structured domain objects that have already been
collected and extracted by the services package — it never touches raw
data or performs its own data collection.

Unlike the services package, failures here are NOT swallowed into a
graceful-but-empty result: see errors.py / OrchestratorError. A wrong or
fabricated diagnosis, strategy, or report is worse than an honest
failure.

Implemented (Brick 8 + Brick 9 — orchestrator is now feature-complete
for V1's reasoning pipeline; Brick 10 adds PowerPoint export on top):
- main_llm_client                  -> generate_json_response_from_main_llm()
- context_builders                 -> build_extracted_information_context(), build_market_research_context(), build_diagnosis_context()
- business_diagnosis_generator     -> analyze_company_business_case()
- marketing_strategy_generator     -> generate_marketing_strategy() (the "yes" and "override" paths)
- report_generator                 -> generate_business_diagnosis_report() (the yes/no decision + report composition),
                                       generate_marketing_strategy_report_despite_diagnosis() (the explicit override path)

Planned next (Brick 10):
- powerpoint_generator_service (in services/, since it's a rendering
  concern, not a reasoning one)
"""

from orchestrator.business_diagnosis_generator import (
    analyze_company_business_case,
    analyze_company_business_case_for_consulting_case,
)
from orchestrator.errors import OrchestratorError
from orchestrator.main_llm_client import MainLlmClientError, generate_json_response_from_main_llm
from orchestrator.marketing_strategy_generator import (
    generate_marketing_strategy,
    generate_marketing_strategy_for_consulting_case,
)
from orchestrator.report_generator import (
    generate_business_diagnosis_report,
    generate_business_diagnosis_report_for_consulting_case,
    generate_marketing_strategy_report_despite_diagnosis,
    generate_marketing_strategy_report_despite_diagnosis_for_consulting_case,
)

__all__ = [
    "MainLlmClientError",
    "OrchestratorError",
    "analyze_company_business_case",
    "analyze_company_business_case_for_consulting_case",
    "generate_business_diagnosis_report",
    "generate_business_diagnosis_report_for_consulting_case",
    "generate_json_response_from_main_llm",
    "generate_marketing_strategy",
    "generate_marketing_strategy_for_consulting_case",
    "generate_marketing_strategy_report_despite_diagnosis",
    "generate_marketing_strategy_report_despite_diagnosis_for_consulting_case",
]
