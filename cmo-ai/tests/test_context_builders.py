"""
Tests for the shared prompt-context builders (Brick 9).

build_extracted_information_context and build_market_research_context
were relocated here from business_diagnosis_generator.py in Brick 9 so
the marketing strategy generator can reuse them without duplication;
their behavior is unchanged and still covered by
test_business_diagnosis_generator.py. This file adds coverage for the
new build_diagnosis_context.
"""

from __future__ import annotations

from domain import (
    BusinessDiagnosis,
    ConfidenceLevel,
    Finding,
    MarketingNecessityDecision,
)
from orchestrator.context_builders import build_diagnosis_context


def _make_diagnosis(**overrides) -> BusinessDiagnosis:
    defaults = dict(
        consulting_case_id="case-1",
        decision=MarketingNecessityDecision.MARKETING_IS_THE_PRIMARY_ISSUE,
        primary_bottleneck="Low brand awareness in an otherwise well-served segment.",
        reasoning_summary="Product and pricing are competitive; awareness is the gap.",
        confidence=ConfidenceLevel.MEDIUM,
    )
    defaults.update(overrides)
    return BusinessDiagnosis(**defaults)


def test_build_diagnosis_context_includes_core_fields():
    diagnosis = _make_diagnosis()
    block = build_diagnosis_context(diagnosis)

    assert "Decision: marketing_is_the_primary_issue" in block
    assert "Primary bottleneck: Low brand awareness" in block
    assert "Reasoning: Product and pricing are competitive" in block
    assert "Confidence: medium" in block


def test_build_diagnosis_context_omits_findings_line_when_empty():
    diagnosis = _make_diagnosis()
    block = build_diagnosis_context(diagnosis)

    assert "Supporting findings" not in block


def test_build_diagnosis_context_includes_finding_descriptions():
    diagnosis = _make_diagnosis(
        supporting_findings=[
            Finding(
                description="No blog or content marketing found",
                evidence="No blog page discoverable on the website",
                confidence=ConfidenceLevel.MEDIUM,
            ),
            Finding(
                description="Pricing is competitive with named rivals",
                evidence="$29/mo vs competitor's $35/mo",
                confidence=ConfidenceLevel.HIGH,
            ),
        ]
    )
    block = build_diagnosis_context(diagnosis)

    assert "Supporting findings: No blog or content marketing found; Pricing is competitive with named rivals" in block
