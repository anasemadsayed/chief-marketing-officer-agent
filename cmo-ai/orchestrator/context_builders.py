"""
Shared prompt-context formatting helpers.

Both the diagnosis generator (Brick 8) and the marketing strategy
generator (Brick 9) need to render the same domain objects
(ExtractedCompanyInformation, MarketResearch) as plain text for their
prompts, plus the strategy generator additionally needs to render the
BusinessDiagnosis itself. Centralizing that formatting here avoids
duplicating it across orchestrator modules.

These functions do pure mechanical formatting — labeling and joining
already-structured fields into readable text. They perform no
summarization, interpretation, or judgment of their own.
"""

from __future__ import annotations

from domain import BusinessDiagnosis, ExtractedCompanyInformation, MarketResearch


def build_extracted_information_context(info: ExtractedCompanyInformation) -> str:
    """Render the cleaned company information as labeled plain text for a prompt."""
    lines: list[str] = []

    if info.company_description_summary:
        lines.append(f"Description: {info.company_description_summary}")
    if info.value_proposition:
        lines.append(f"Value proposition: {info.value_proposition}")
    if info.products_and_services:
        lines.append("Products/services: " + "; ".join(info.products_and_services))
    if info.unique_selling_points:
        lines.append("Unique selling points: " + "; ".join(info.unique_selling_points))
    if info.target_audience_signals:
        lines.append("Target audience signals: " + "; ".join(info.target_audience_signals))
    if info.pricing_information:
        lines.append("Pricing information: " + "; ".join(info.pricing_information))
    if info.notable_content_snippets:
        lines.append("Notable snippets: " + " | ".join(info.notable_content_snippets))

    return "\n".join(lines)


def build_market_research_context(research: MarketResearch) -> str:
    """Render the market research as labeled plain text for a prompt."""
    lines: list[str] = []

    if research.industry_overview:
        lines.append(f"Industry: {research.industry_overview}")
    if research.competitors:
        competitor_descriptions = [
            f"{competitor.name}" + (f" ({competitor.notes})" if competitor.notes else "")
            for competitor in research.competitors
        ]
        lines.append("Competitors: " + "; ".join(competitor_descriptions))
    if research.target_audience_characteristics:
        lines.append("Market-level audience traits: " + "; ".join(research.target_audience_characteristics))
    if research.market_trends:
        lines.append("Market trends: " + "; ".join(research.market_trends))
    if research.additional_notes:
        lines.append("Additional notes: " + "; ".join(research.additional_notes))

    return "\n".join(lines)


def build_diagnosis_context(diagnosis: BusinessDiagnosis) -> str:
    """Render the business diagnosis as labeled plain text context for the strategy prompt."""
    lines: list[str] = [
        f"Decision: {diagnosis.decision.value}",
        f"Primary bottleneck: {diagnosis.primary_bottleneck}",
        f"Reasoning: {diagnosis.reasoning_summary}",
        f"Confidence: {diagnosis.confidence.value}",
    ]
    if diagnosis.supporting_findings:
        finding_descriptions = [finding.description for finding in diagnosis.supporting_findings]
        lines.append("Supporting findings: " + "; ".join(finding_descriptions))

    return "\n".join(lines)
