"""
Social Media Collector Service.

Pure collection: given a LinkedIn, Facebook, or Instagram profile URL,
fetches whatever public content is available and stores it as a raw
CollectedSource.

Collection strategy (hybrid, with graceful degradation):

    1. If Agent-Reach integration is enabled (the default), try the
       Agent-Reach tool ecosystem first — Jina Reader for LinkedIn,
       opencli for Facebook and Instagram. These tools use headless
       browsers and authenticated sessions to bypass the login walls
       that block simple HTTP requests.

    2. If Agent-Reach is not installed, not configured, or fails for
       any reason, fall back to the original requests+BeautifulSoup
       codepath that extracts Open Graph / Twitter Card meta tags.
       This yields less content but never crashes the pipeline.

This service never interprets, summarizes, or judges the content — that
is the Information Extraction Service's job (Brick 7).
"""

from __future__ import annotations

import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup

from config.settings import settings
from domain import CollectedSource, InformationSourceType
from services.agent_reach_client import fetch_social_profile_via_agent_reach
from storage.collected_source_repository import create_and_save_collected_source

logger = logging.getLogger(__name__)

# Map from our domain enum to the Agent-Reach platform name expected by
# the client module's dispatch function.
_PLATFORM_NAME_MAP: dict[InformationSourceType, str] = {
    InformationSourceType.LINKEDIN_PROFILE: "linkedin",
    InformationSourceType.FACEBOOK_PROFILE: "facebook",
    InformationSourceType.INSTAGRAM_PROFILE: "instagram",
}

# Meta tag names/properties checked, in priority order, to build the
# "preview" section of the collected content. Open Graph first, since
# it's the most widely and reliably populated by these platforms.
_PREVIEW_META_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("property", "og:title", "Title"),
    ("property", "og:site_name", "Site Name"),
    ("property", "og:description", "Description"),
    ("name", "twitter:title", "Title (Twitter Card)"),
    ("name", "twitter:description", "Description (Twitter Card)"),
    ("name", "description", "Description (Meta)"),
)

_HTML_CONTENT_TYPE_MARKERS: tuple[str, ...] = ("text/html", "application/xhtml")

_NON_CONTENT_TAGS: tuple[str, ...] = ("script", "style", "noscript", "svg", "iframe")


def collect_social_media_profiles_for_consulting_case(
    consulting_case_id: str,
    linkedin_url: Optional[str] = None,
    facebook_url: Optional[str] = None,
    instagram_url: Optional[str] = None,
) -> list[CollectedSource]:
    """
    Collect whichever social media profiles were actually provided for
    this consulting case. Profiles that weren't provided are silently
    skipped (not attempted, not stored as failures).
    """
    platform_urls: tuple[tuple[InformationSourceType, Optional[str]], ...] = (
        (InformationSourceType.LINKEDIN_PROFILE, linkedin_url),
        (InformationSourceType.FACEBOOK_PROFILE, facebook_url),
        (InformationSourceType.INSTAGRAM_PROFILE, instagram_url),
    )

    collected_sources: list[CollectedSource] = []
    for platform, profile_url in platform_urls:
        if profile_url:
            collected_sources.append(
                collect_social_media_profile_content(consulting_case_id, platform, profile_url)
            )
    return collected_sources


def collect_social_media_profile_content(
    consulting_case_id: str,
    platform: InformationSourceType,
    profile_url: str,
) -> CollectedSource:
    """
    Fetch one social media profile URL and store whatever public content
    (preview meta tags + visible text) is available as a CollectedSource.

    Uses a two-tier collection strategy:

    1. **Agent-Reach** (if enabled): invoke the appropriate upstream tool
       (Jina Reader, opencli, or mcporter) to get rich, authenticated
       profile content. This is far more likely to succeed against
       LinkedIn/Facebook/Instagram login walls.

    2. **Fallback** (requests + BeautifulSoup): extract Open Graph and
       Twitter Card meta tags from whatever HTML the platform returns to
       a plain HTTP request. Usually yields only the preview snippet.

    On any failure — network error, non-2xx response, non-HTML content —
    a CollectedSource is still saved with collection_successful=False and
    an explanatory error message, the same pattern used by the website
    and PDF collectors.
    """
    logger.info(
        "Collecting %s content for case=%s url=%s", platform.value, consulting_case_id, profile_url
    )

    # ── Tier 1: Agent-Reach ──────────────────────────────────────────
    if settings.agent_reach_enabled:
        agent_reach_platform = _PLATFORM_NAME_MAP.get(platform)
        if agent_reach_platform:
            content, error = fetch_social_profile_via_agent_reach(agent_reach_platform, profile_url)
            if content:
                logger.info(
                    "Agent-Reach successfully collected %s content (%d chars) for case=%s",
                    platform.value,
                    len(content),
                    consulting_case_id,
                )
                return create_and_save_collected_source(
                    consulting_case_id=consulting_case_id,
                    source_type=platform,
                    source_url_or_path=profile_url,
                    raw_content=content,
                    collection_successful=True,
                )
            logger.info(
                "Agent-Reach could not collect %s at %s (%s), falling back to basic scraper",
                platform.value,
                profile_url,
                error,
            )

    # ── Tier 2: basic OG-meta fallback ───────────────────────────────
    html, error = _fetch_profile_page_html(profile_url)

    if html is None:
        logger.warning("Failed to collect %s at %s: %s", platform.value, profile_url, error)
        return create_and_save_collected_source(
            consulting_case_id=consulting_case_id,
            source_type=platform,
            source_url_or_path=profile_url,
            raw_content="",
            collection_successful=False,
            collection_error_message=error,
        )

    raw_content = _build_profile_raw_content(html)

    if not raw_content:
        logger.info(
            "%s at %s returned no usable preview data or visible text "
            "(likely a login wall) — stored as an empty successful collection",
            platform.value, profile_url,
        )

    return create_and_save_collected_source(
        consulting_case_id=consulting_case_id,
        source_type=platform,
        source_url_or_path=profile_url,
        raw_content=raw_content,
        collection_successful=True,
    )


# ── Fallback helpers (unchanged from the original implementation) ────

def _fetch_profile_page_html(url: str) -> tuple[Optional[str], Optional[str]]:
    """
    Fetch one URL. Returns (html, None) on success or (None, error_message)
    on any failure (network error, non-2xx status, non-HTML content type).
    """
    try:
        response = requests.get(
            url,
            headers={"User-Agent": settings.social_media_collector_user_agent},
            timeout=settings.social_media_collector_timeout_seconds,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as error:
        return None, str(error)

    content_type = response.headers.get("Content-Type", "")
    if not any(marker in content_type for marker in _HTML_CONTENT_TYPE_MARKERS):
        return None, f"Unsupported content type: {content_type or 'unknown'}"

    return response.text, None


def _build_profile_raw_content(html: str) -> str:
    """
    Combine the page's preview meta tags (Open Graph / Twitter Card /
    plain meta description) with its visible text into one raw content
    block. Meta tags come first since they're the most reliable signal
    for these platforms and survive even when the body is a login wall.
    """
    soup = BeautifulSoup(html, "lxml")

    preview_lines = _extract_preview_meta_lines(soup)
    visible_text = _extract_visible_text_from_html(soup)

    sections = []
    if preview_lines:
        sections.append("\n".join(preview_lines))
    if visible_text:
        sections.append(f"--- Visible Page Text ---\n{visible_text}")

    return "\n\n".join(sections)


def _extract_preview_meta_lines(soup: BeautifulSoup) -> list[str]:
    """Pull whichever preview meta fields are present, in priority order, deduped by label."""
    seen_labels: set[str] = set()
    lines: list[str] = []

    for attribute_name, attribute_value, label in _PREVIEW_META_FIELDS:
        base_label = label.split(" (")[0]  # e.g. "Title (Twitter Card)" -> "Title"
        if base_label in seen_labels:
            continue

        tag = soup.find("meta", attrs={attribute_name: attribute_value})
        content = tag.get("content", "").strip() if tag else ""
        if content:
            lines.append(f"{label}: {content}")
            seen_labels.add(base_label)

    if not lines and soup.title and soup.title.string:
        lines.append(f"Page Title: {soup.title.string.strip()}")

    return lines


def _extract_visible_text_from_html(soup: BeautifulSoup) -> str:
    """
    Strip non-content markup (script/style/etc.) and return meaningful visible text.
    Filters out massive multi-language footers and boilerplate login wall noise.
    """
    for tag in soup(_NON_CONTENT_TAGS):
        tag.decompose()

    raw_text = soup.get_text(separator="\n")
    meaningful_lines = []
    
    # Common internationalization language dumps on Instagram/Facebook login walls
    noise_tokens = {
        "afrikaans", "čeština", "dansk", "deutsch", "ελληνικά", "español", "suomi",
        "français", "עברית", "bahasa indonesia", "italiano", "日本語", "한국어",
        "bahasa melayu", "norsk", "nederlands", "polski", "português", "русский",
        "svenska", "ภาษาไทย", "filipino", "türkçe", "中文", "বাংলা", "ગુજરાતી",
        "हिन्दी", "hrvatski", "magyar", "ಕನ್ನಡ", "മലയാളം", "मराठी", "नेपाली",
        "ਪੰਜਾਬੀ", "සිංහල", "slovenčina", "தமிழ்", "తెలుగు", "اردو", "tiếng việt",
        "български", "română", "српски", "українська"
    }

    for line in raw_text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        # Drop language picker noise
        if cleaned.lower() in noise_tokens:
            continue
        meaningful_lines.append(cleaned)

    return "\n".join(meaningful_lines)
