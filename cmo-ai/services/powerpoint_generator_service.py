"""
PowerPoint Generator Service.

Takes a completed GeneratedReport (diagnosis, and strategy if one was
generated) and renders it as a polished .pptx deliverable using
python-pptx. This is a pure rendering concern, not a reasoning one — the
content itself was already decided by the orchestrator (Bricks 8-9);
this service only lays it out visually.

Uses python-pptx rather than a Node.js toolchain deliberately: this
service ships as part of the user's own Python application and must run
with nothing beyond the packages in requirements.txt.

Handles both report types produced by Brick 9:
- DIAGNOSIS_ONLY: title, diagnosis verdict, supporting evidence, closing.
- DIAGNOSIS_AND_STRATEGY: the above, plus (when the strategy carries an
  override disclaimer) a dedicated override-notice slide, an executive
  summary slide, an objectives-and-channels slide, one or more key
  initiatives slides, and any strategy-level supporting evidence.

Like the other services (not the orchestrator), rendering failures
degrade gracefully: a missing PowerPoint export doesn't invalidate the
diagnosis/strategy that's still fully present in the database. The
convenience wrapper catches PowerPointGenerationError and returns the
report unchanged (without a powerpoint_file_path) rather than crashing
the pipeline.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.slide import Slide
from pptx.util import Inches, Pt

from config.settings import settings
from domain import (
    BusinessDiagnosis,
    Finding,
    GeneratedReport,
    MarketingNecessityDecision,
    MarketingStrategy,
    StrategyInitiative,
)
from storage.generated_report_repository import (
    get_generated_report_by_case_id,
    save_generated_report,
)

logger = logging.getLogger(__name__)

# -- "Midnight Executive" palette: one dominant color (navy), one supporting
# tone (ice blue), white, plus a small set of semantic accents. -------------
_COLOR_NAVY = RGBColor.from_string("1E2761")
_COLOR_ICE_BLUE = RGBColor.from_string("CADCFC")
_COLOR_WHITE = RGBColor.from_string("FFFFFF")
_COLOR_CHARCOAL_TEXT = RGBColor.from_string("2B2B33")
_COLOR_MUTED_GRAY = RGBColor.from_string("6B7280")
_COLOR_GO_GREEN = RGBColor.from_string("1F7A4D")
_COLOR_NEUTRAL_SLATE = RGBColor.from_string("5C6B73")
_COLOR_MOTIF_TINT = RGBColor.from_string("EDF1FA")
_COLOR_DARK_MOTIF_TINT = RGBColor.from_string("2A3577")  # tone-on-tone lighter navy, for dark slides
_COLOR_WARNING_AMBER = RGBColor.from_string("E8A33D")
_COLOR_WARNING_TEXT = RGBColor.from_string("5C3D0E")
_COLOR_CARD_BACKGROUND = RGBColor.from_string("F4F6FB")

_SLIDE_WIDTH_INCHES = 13.333
_SLIDE_HEIGHT_INCHES = 7.5
_MARGIN_INCHES = 0.6
_CONTENT_WIDTH_INCHES = 7.6

_MAX_FINDINGS_PER_SLIDE = 4
_MAX_INITIATIVES_PER_SLIDE = 4

_TITLE_FONT = "Cambria"
_BODY_FONT = "Calibri"


class PowerPointGenerationError(RuntimeError):
    """Raised when the .pptx file could not be produced."""


def create_business_consulting_presentation(
    report: GeneratedReport,
    company_name: str,
    output_path: str,
) -> str:
    """
    Render the given report as a .pptx file at output_path.

    Renders DIAGNOSIS_ONLY reports as title/diagnosis/evidence/closing.
    Renders DIAGNOSIS_AND_STRATEGY reports as the above plus (in order)
    an override-notice slide when the strategy carries one, an executive
    summary slide, an objectives-and-channels slide, one or more key
    initiatives slides, and any strategy-level supporting evidence.

    Raises PowerPointGenerationError on any failure (bad output path,
    unexpected python-pptx error). Returns output_path on success.
    """
    try:
        presentation = Presentation()
        presentation.slide_width = Inches(_SLIDE_WIDTH_INCHES)
        presentation.slide_height = Inches(_SLIDE_HEIGHT_INCHES)

        _add_title_slide(presentation, company_name, report)
        _add_diagnosis_slide(presentation, report.diagnosis)

        for findings_chunk in _chunk_list(report.diagnosis.supporting_findings, _MAX_FINDINGS_PER_SLIDE):
            _add_findings_slide(presentation, "Supporting Evidence", findings_chunk)

        if report.strategy is not None:
            if report.strategy.override_warning_message:
                _add_override_notice_slide(presentation, report.strategy)

            _add_executive_summary_slide(presentation, report.strategy)
            _add_objectives_and_channels_slide(presentation, report.strategy)

            for initiatives_chunk in _chunk_list(report.strategy.key_initiatives, _MAX_INITIATIVES_PER_SLIDE):
                _add_key_initiatives_slide(presentation, initiatives_chunk)

            for findings_chunk in _chunk_list(report.strategy.supporting_findings, _MAX_FINDINGS_PER_SLIDE):
                _add_findings_slide(presentation, "Strategy Evidence", findings_chunk)

        _add_closing_slide(presentation, report.consulting_case_id)

        output_file_path = Path(output_path)
        output_file_path.parent.mkdir(parents=True, exist_ok=True)
        presentation.save(str(output_file_path))
    except Exception as error:  # noqa: BLE001 - any rendering failure must not crash the caller
        raise PowerPointGenerationError(
            f"Could not generate PowerPoint for output_path='{output_path}': {error}"
        ) from error

    logger.info("PowerPoint generated for case=%s at %s", report.consulting_case_id, output_path)
    return str(output_file_path)


def create_business_consulting_presentation_for_consulting_case(
    consulting_case_id: str,
    company_name: str,
    output_directory: Optional[str] = None,
) -> GeneratedReport:
    """
    Convenience entry point for the main pipeline: fetches the already-
    generated report from storage, renders it, updates and re-saves the
    report's powerpoint_file_path, and returns the updated report.

    If rendering fails (PowerPointGenerationError), the error is logged
    and the ORIGINAL report is returned unchanged (powerpoint_file_path
    left as it was) — the diagnosis and strategy are still fully valid
    and usable without the slide deck, so this never raises for
    rendering failures. It does raise if no report exists yet to render.
    """
    report = get_generated_report_by_case_id(consulting_case_id)
    if report is None:
        raise PowerPointGenerationError(
            f"Cannot generate a PowerPoint for case '{consulting_case_id}': no "
            "generated report found. Run report generation first."
        )

    output_dir = Path(output_directory) if output_directory else settings.powerpoint_output_directory_path
    output_path = output_dir / f"{consulting_case_id}.pptx"

    try:
        saved_path = create_business_consulting_presentation(report, company_name, str(output_path))
    except PowerPointGenerationError as error:
        logger.warning(
            "PowerPoint generation failed for case=%s; report remains valid without a deck: %s",
            consulting_case_id, error,
        )
        return report

    updated_report = report.model_copy(update={"powerpoint_file_path": saved_path})
    save_generated_report(updated_report)
    return updated_report


# --- Slide builders ----------------------------------------------------------


def _add_blank_slide(presentation: Presentation) -> Slide:
    blank_layout = presentation.slide_layouts[6]
    return presentation.slides.add_slide(blank_layout)


def _set_slide_background(slide: Slide, color: RGBColor) -> None:
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = color


def _add_textbox(
    slide: Slide,
    left: float,
    top: float,
    width: float,
    height: float,
    text: str,
    *,
    font_name: str = _BODY_FONT,
    font_size: int = 16,
    bold: bool = False,
    italic: bool = False,
    color: RGBColor = _COLOR_CHARCOAL_TEXT,
    align: PP_ALIGN = PP_ALIGN.LEFT,
    anchor: Optional[MSO_ANCHOR] = None,
):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    frame = box.text_frame
    frame.word_wrap = True
    if anchor is not None:
        frame.vertical_anchor = anchor
    paragraph = frame.paragraphs[0]
    paragraph.alignment = align
    run = paragraph.add_run()
    run.text = text
    run.font.name = font_name
    run.font.size = Pt(font_size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    return box


def _add_badge(
    slide: Slide, left: float, top: float, width: float, text: str,
    fill_color: RGBColor, text_color: RGBColor = _COLOR_WHITE,
) -> None:
    """A small rounded-rectangle 'pill' used for decision/confidence badges."""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(0.45)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    shape.line.fill.background()
    shape.shadow.inherit = False
    frame = shape.text_frame
    frame.word_wrap = True
    frame.margin_left = 0
    frame.margin_right = 0
    paragraph = frame.paragraphs[0]
    paragraph.alignment = PP_ALIGN.CENTER
    run = paragraph.add_run()
    run.text = text
    run.font.name = _BODY_FONT
    run.font.size = Pt(14)
    run.font.bold = True
    run.font.color.rgb = text_color


def _add_bullet_circle(slide: Slide, left: float, top: float, color: RGBColor) -> None:
    """Small filled circle used as the deck's repeated visual motif for list items."""
    diameter = 0.16
    circle = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(left), Inches(top), Inches(diameter), Inches(diameter))
    circle.fill.solid()
    circle.fill.fore_color.rgb = color
    circle.line.fill.background()
    circle.shadow.inherit = False


def _add_side_motif(slide: Slide) -> None:
    """
    Large soft circle (plus a small solid accent) in the slide's right
    margin — the same circle motif used for section headers and list
    items, scaled up. Added first so text renders on top. Keeps content
    text boxes to _CONTENT_WIDTH_INCHES rather than the full slide
    width, so light-background slides get a visual element beyond text
    and don't read as unbalanced when the content itself is short.
    """
    big_diameter = 4.6
    big_left = _SLIDE_WIDTH_INCHES - _MARGIN_INCHES - big_diameter + 0.9
    big_top = (_SLIDE_HEIGHT_INCHES - big_diameter) / 2 + 0.2
    big_circle = slide.shapes.add_shape(
        MSO_SHAPE.OVAL, Inches(big_left), Inches(big_top), Inches(big_diameter), Inches(big_diameter)
    )
    big_circle.fill.solid()
    big_circle.fill.fore_color.rgb = _COLOR_MOTIF_TINT
    big_circle.line.fill.background()
    big_circle.shadow.inherit = False

    small_diameter = 1.3
    small_left = big_left + big_diameter - small_diameter - 0.3
    small_top = big_top + big_diameter - small_diameter - 0.2
    small_circle = slide.shapes.add_shape(
        MSO_SHAPE.OVAL, Inches(small_left), Inches(small_top), Inches(small_diameter), Inches(small_diameter)
    )
    small_circle.fill.solid()
    small_circle.fill.fore_color.rgb = _COLOR_NAVY
    small_circle.line.fill.background()
    small_circle.shadow.inherit = False


def _add_dark_side_motif(slide: Slide) -> None:
    """
    Same repeated circle motif as _add_side_motif, adapted for navy
    (title/closing) backgrounds: a tone-on-tone lighter-navy circle
    plus an ice-blue accent circle, instead of the light-tint version
    used on white slides. Keeps the motif consistent across every slide
    in the deck rather than leaving the dark bookend slides bare.
    """
    big_diameter = 4.6
    big_left = _SLIDE_WIDTH_INCHES - _MARGIN_INCHES - big_diameter + 0.9
    big_top = (_SLIDE_HEIGHT_INCHES - big_diameter) / 2 + 0.2
    big_circle = slide.shapes.add_shape(
        MSO_SHAPE.OVAL, Inches(big_left), Inches(big_top), Inches(big_diameter), Inches(big_diameter)
    )
    big_circle.fill.solid()
    big_circle.fill.fore_color.rgb = _COLOR_DARK_MOTIF_TINT
    big_circle.line.fill.background()
    big_circle.shadow.inherit = False

    small_diameter = 1.3
    small_left = big_left + big_diameter - small_diameter - 0.3
    small_top = big_top + big_diameter - small_diameter - 0.2
    small_circle = slide.shapes.add_shape(
        MSO_SHAPE.OVAL, Inches(small_left), Inches(small_top), Inches(small_diameter), Inches(small_diameter)
    )
    small_circle.fill.solid()
    small_circle.fill.fore_color.rgb = _COLOR_ICE_BLUE
    small_circle.line.fill.background()
    small_circle.shadow.inherit = False


def _add_section_header(slide: Slide, text: str) -> None:
    _add_bullet_circle(slide, _MARGIN_INCHES, 0.62, _COLOR_NAVY)
    _add_textbox(
        slide, _MARGIN_INCHES + 0.3, 0.45, _CONTENT_WIDTH_INCHES - 0.3, 0.6,
        text, font_name=_TITLE_FONT, font_size=24, bold=True, color=_COLOR_NAVY,
    )


def _add_title_slide(presentation: Presentation, company_name: str, report: GeneratedReport) -> None:
    slide = _add_blank_slide(presentation)
    _set_slide_background(slide, _COLOR_NAVY)
    _add_dark_side_motif(slide)

    subtitle = (
        "Business Diagnosis & Marketing Strategy"
        if report.strategy is not None
        else "Business Diagnosis Report"
    )

    _add_textbox(
        slide, _MARGIN_INCHES, 2.6, _SLIDE_WIDTH_INCHES - 2 * _MARGIN_INCHES, 1.4,
        company_name, font_name=_TITLE_FONT, font_size=44, bold=True, color=_COLOR_WHITE,
    )
    _add_textbox(
        slide, _MARGIN_INCHES, 3.9, _SLIDE_WIDTH_INCHES - 2 * _MARGIN_INCHES, 0.7,
        subtitle, font_name=_BODY_FONT, font_size=20, color=_COLOR_ICE_BLUE,
    )
    _add_textbox(
        slide, _MARGIN_INCHES, _SLIDE_HEIGHT_INCHES - 1.0, _SLIDE_WIDTH_INCHES - 2 * _MARGIN_INCHES, 0.5,
        f"Prepared by cmoAI  |  {report.generated_at.strftime('%B %d, %Y')}",
        font_name=_BODY_FONT, font_size=12, color=_COLOR_ICE_BLUE,
    )


def _add_diagnosis_slide(presentation: Presentation, diagnosis: BusinessDiagnosis) -> None:
    slide = _add_blank_slide(presentation)
    _set_slide_background(slide, _COLOR_WHITE)
    _add_side_motif(slide)
    _add_section_header(slide, "Diagnosis")

    decision_is_marketing = diagnosis.decision == MarketingNecessityDecision.MARKETING_IS_THE_PRIMARY_ISSUE
    decision_text = (
        "MARKETING IS THE PRIMARY ISSUE" if decision_is_marketing else "MARKETING IS NOT THE PRIMARY ISSUE"
    )
    decision_color = _COLOR_GO_GREEN if decision_is_marketing else _COLOR_NEUTRAL_SLATE

    _add_textbox(
        slide, _MARGIN_INCHES, 1.5, _CONTENT_WIDTH_INCHES, 1.3,
        decision_text, font_name=_TITLE_FONT, font_size=28, bold=True, color=decision_color,
    )

    confidence_label = f"Confidence: {diagnosis.confidence.value.upper()}"
    _add_badge(slide, _MARGIN_INCHES, 2.75, 2.6, confidence_label, _COLOR_NAVY)

    _add_textbox(
        slide, _MARGIN_INCHES, 3.55, _CONTENT_WIDTH_INCHES, 0.4,
        "Primary Bottleneck", font_name=_BODY_FONT, font_size=14, bold=True, color=_COLOR_MUTED_GRAY,
    )
    _add_textbox(
        slide, _MARGIN_INCHES, 3.95, _CONTENT_WIDTH_INCHES, 1.0,
        diagnosis.primary_bottleneck, font_name=_BODY_FONT, font_size=18, color=_COLOR_CHARCOAL_TEXT,
    )

    _add_textbox(
        slide, _MARGIN_INCHES, 5.05, _CONTENT_WIDTH_INCHES, 0.4,
        "Reasoning", font_name=_BODY_FONT, font_size=14, bold=True, color=_COLOR_MUTED_GRAY,
    )
    _add_textbox(
        slide, _MARGIN_INCHES, 5.45, _CONTENT_WIDTH_INCHES, 1.9,
        diagnosis.reasoning_summary, font_name=_BODY_FONT, font_size=13, color=_COLOR_CHARCOAL_TEXT,
    )


def _add_findings_slide(presentation: Presentation, title: str, findings: list[Finding]) -> None:
    slide = _add_blank_slide(presentation)
    _set_slide_background(slide, _COLOR_WHITE)
    _add_side_motif(slide)
    _add_section_header(slide, title)

    row_top = 1.6
    row_height = 1.3
    for finding in findings:
        _add_bullet_circle(slide, _MARGIN_INCHES, row_top + 0.08, _COLOR_NAVY)
        _add_textbox(
            slide, _MARGIN_INCHES + 0.35, row_top - 0.08, _CONTENT_WIDTH_INCHES - 0.35, 0.4,
            finding.description, font_name=_BODY_FONT, font_size=15, bold=True, color=_COLOR_CHARCOAL_TEXT,
        )
        _add_textbox(
            slide, _MARGIN_INCHES + 0.35, row_top + 0.38, _CONTENT_WIDTH_INCHES - 0.35, 0.75,
            finding.evidence, font_name=_BODY_FONT, font_size=12, italic=True, color=_COLOR_MUTED_GRAY,
        )
        row_top += row_height


def _add_override_notice_slide(presentation: Presentation, strategy: MarketingStrategy) -> None:
    """
    A dedicated call-out slide for the override path: the diagnosis said
    marketing was NOT the primary issue, but the user asked for a
    strategy anyway. The full-width amber banner IS this slide's visual
    element by design, so it deliberately skips the side-motif circle
    and section header used elsewhere — a second decoration would just
    compete with the banner rather than add anything.
    """
    slide = _add_blank_slide(presentation)
    _set_slide_background(slide, _COLOR_WHITE)

    banner = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE,
        Inches(_MARGIN_INCHES), Inches(1.4),
        Inches(_SLIDE_WIDTH_INCHES - 2 * _MARGIN_INCHES), Inches(4.2),
    )
    banner.fill.solid()
    banner.fill.fore_color.rgb = _COLOR_WARNING_AMBER
    banner.line.fill.background()
    banner.shadow.inherit = False

    frame = banner.text_frame
    frame.word_wrap = True
    frame.vertical_anchor = MSO_ANCHOR.MIDDLE
    frame.margin_left = Inches(0.5)
    frame.margin_right = Inches(0.5)

    heading_paragraph = frame.paragraphs[0]
    heading_paragraph.alignment = PP_ALIGN.LEFT
    heading_run = heading_paragraph.add_run()
    heading_run.text = "Requested Despite Diagnosis"
    heading_run.font.name = _TITLE_FONT
    heading_run.font.size = Pt(26)
    heading_run.font.bold = True
    heading_run.font.color.rgb = _COLOR_WARNING_TEXT

    body_paragraph = frame.add_paragraph()
    body_paragraph.alignment = PP_ALIGN.LEFT
    body_paragraph.space_before = Pt(16)
    body_run = body_paragraph.add_run()
    body_run.text = strategy.override_warning_message or ""
    body_run.font.name = _BODY_FONT
    body_run.font.size = Pt(16)
    body_run.font.color.rgb = _COLOR_WARNING_TEXT


def _add_executive_summary_slide(presentation: Presentation, strategy: MarketingStrategy) -> None:
    slide = _add_blank_slide(presentation)
    _set_slide_background(slide, _COLOR_WHITE)
    _add_side_motif(slide)
    _add_section_header(slide, "Marketing Strategy")

    _add_textbox(
        slide, _MARGIN_INCHES, 1.6, _CONTENT_WIDTH_INCHES, 0.4,
        "Executive Summary", font_name=_BODY_FONT, font_size=14, bold=True, color=_COLOR_MUTED_GRAY,
    )
    _add_textbox(
        slide, _MARGIN_INCHES, 2.2, _CONTENT_WIDTH_INCHES, 4.3,
        strategy.executive_summary, font_name=_BODY_FONT, font_size=22, color=_COLOR_CHARCOAL_TEXT,
        anchor=MSO_ANCHOR.TOP,
    )


def _add_objectives_and_channels_slide(presentation: Presentation, strategy: MarketingStrategy) -> None:
    """
    Two-column layout spanning the full slide width. Deliberately skips
    the side-motif circle used on narrower single-column slides — the
    two columns of content are this slide's own visual variety, and a
    background circle would only clutter the right column's text.
    """
    slide = _add_blank_slide(presentation)
    _set_slide_background(slide, _COLOR_WHITE)
    _add_section_header(slide, "Objectives & Channels")

    column_width = (_SLIDE_WIDTH_INCHES - 2 * _MARGIN_INCHES - 0.5) / 2

    _add_textbox(
        slide, _MARGIN_INCHES, 1.6, column_width, 0.4,
        "Strategic Objectives", font_name=_BODY_FONT, font_size=16, bold=True, color=_COLOR_NAVY,
    )
    _add_bulleted_list(slide, _MARGIN_INCHES, 2.1, column_width, strategy.strategic_objectives)

    right_column_left = _MARGIN_INCHES + column_width + 0.5
    _add_textbox(
        slide, right_column_left, 1.6, column_width, 0.4,
        "Recommended Channels", font_name=_BODY_FONT, font_size=16, bold=True, color=_COLOR_NAVY,
    )
    _add_bulleted_list(slide, right_column_left, 2.1, column_width, strategy.recommended_channels)


def _add_bulleted_list(slide: Slide, left: float, top: float, width: float, items: list[str]) -> None:
    """A simple circle-bulleted list, one row per item — the building block for text-list slides."""
    row_top = top
    for item in items:
        _add_bullet_circle(slide, left, row_top + 0.08, _COLOR_NAVY)
        _add_textbox(
            slide, left + 0.3, row_top - 0.08, width - 0.3, 0.55,
            item, font_name=_BODY_FONT, font_size=14, color=_COLOR_CHARCOAL_TEXT,
        )
        row_top += 0.6


def _add_key_initiatives_slide(presentation: Presentation, initiatives: list[StrategyInitiative]) -> None:
    """
    A 2x2 grid of initiative cards spanning the full slide width. Like
    the objectives/channels slide, this deliberately skips the
    side-motif circle: the card grid itself is the visual element for
    this slide (a layout the pptx skill explicitly recommends), and
    cards would otherwise sit on top of / crowd out the circle.
    """
    slide = _add_blank_slide(presentation)
    _set_slide_background(slide, _COLOR_WHITE)
    _add_section_header(slide, "Key Initiatives")

    content_top = 1.5
    content_width = _SLIDE_WIDTH_INCHES - 2 * _MARGIN_INCHES
    content_height = _SLIDE_HEIGHT_INCHES - content_top - 0.5

    columns = 2
    rows = 2
    gap = 0.3
    card_width = (content_width - gap) / columns
    card_height = (content_height - gap) / rows

    for index, initiative in enumerate(initiatives):
        column = index % columns
        row = index // columns
        card_left = _MARGIN_INCHES + column * (card_width + gap)
        card_top = content_top + row * (card_height + gap)

        card = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, Inches(card_left), Inches(card_top), Inches(card_width), Inches(card_height)
        )
        card.fill.solid()
        card.fill.fore_color.rgb = _COLOR_CARD_BACKGROUND
        card.line.fill.background()
        card.shadow.inherit = False

        frame = card.text_frame
        frame.word_wrap = True
        frame.margin_left = Inches(0.25)
        frame.margin_right = Inches(0.25)
        frame.margin_top = Inches(0.2)

        title_paragraph = frame.paragraphs[0]
        title_paragraph.alignment = PP_ALIGN.LEFT
        title_run = title_paragraph.add_run()
        title_run.text = initiative.title
        title_run.font.name = _BODY_FONT
        title_run.font.size = Pt(16)
        title_run.font.bold = True
        title_run.font.color.rgb = _COLOR_NAVY

        description_paragraph = frame.add_paragraph()
        description_paragraph.space_before = Pt(6)
        description_run = description_paragraph.add_run()
        description_run.text = initiative.description
        description_run.font.name = _BODY_FONT
        description_run.font.size = Pt(12)
        description_run.font.color.rgb = _COLOR_CHARCOAL_TEXT

        if initiative.expected_impact:
            impact_paragraph = frame.add_paragraph()
            impact_paragraph.space_before = Pt(8)
            impact_run = impact_paragraph.add_run()
            impact_run.text = f"Impact: {initiative.expected_impact}"
            impact_run.font.name = _BODY_FONT
            impact_run.font.size = Pt(11)
            impact_run.font.italic = True
            impact_run.font.color.rgb = _COLOR_MUTED_GRAY


def _add_closing_slide(presentation: Presentation, consulting_case_id: str) -> None:
    slide = _add_blank_slide(presentation)
    _set_slide_background(slide, _COLOR_NAVY)
    _add_dark_side_motif(slide)

    _add_textbox(
        slide, _MARGIN_INCHES, 3.1, _SLIDE_WIDTH_INCHES - 2 * _MARGIN_INCHES, 1.0,
        "Thank you", font_name=_TITLE_FONT, font_size=40, bold=True, color=_COLOR_WHITE, align=PP_ALIGN.CENTER,
    )
    _add_textbox(
        slide, _MARGIN_INCHES, 4.1, _SLIDE_WIDTH_INCHES - 2 * _MARGIN_INCHES, 0.5,
        f"Case reference: {consulting_case_id}", font_name=_BODY_FONT, font_size=13, color=_COLOR_ICE_BLUE, align=PP_ALIGN.CENTER,
    )


def _chunk_list(items: list, chunk_size: int) -> list[list]:
    """Split a list into consecutive chunks of at most chunk_size items each."""
    if not items:
        return []
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]
