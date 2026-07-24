"""
Website Collector Service.

Pure collection: given a company's website URL, fetches the homepage
plus a handful of likely-relevant internal pages (about, products,
services, blog, contact, pricing, ...), strips out non-visible technical
markup (script/style/etc.), and stores each page as a raw CollectedSource.

This service never interprets, summarizes, or judges the content — that
is the Information Extraction Service's job (Brick 7). It only decides
*which pages are worth fetching*, not what they mean.
"""

from __future__ import annotations

import logging
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config.settings import settings
from domain import CollectedSource, InformationSourceType
from storage.collected_source_repository import create_and_save_collected_source

logger = logging.getLogger(__name__)

# Keywords used to recognize likely-relevant internal links on the homepage,
# checked against both the link's URL path and its visible link text.
_RELEVANT_PAGE_KEYWORDS: tuple[str, ...] = (
    "about",
    "company",
    "who-we-are",
    "product",
    "service",
    "solution",
    "blog",
    "news",
    "contact",
    "pricing",
    "team",
)

# Common paths tried as a fallback when the homepage's own navigation
# doesn't surface enough relevant links (e.g. a JS-heavy nav menu).
_COMMON_PAGE_PATH_GUESSES: tuple[str, ...] = (
    "/about",
    "/about-us",
    "/products",
    "/services",
    "/blog",
    "/contact",
    "/contact-us",
    "/pricing",
)

_HTML_CONTENT_TYPE_MARKERS: tuple[str, ...] = ("text/html", "application/xhtml")

# Tags that carry no human-readable content and are safe to drop even at
# the "pure collection" stage — this is not interpretation, just removing
# markup that was never visible text to begin with.
_NON_CONTENT_TAGS: tuple[str, ...] = ("script", "style", "noscript", "svg", "iframe")


def collect_website_content_for_consulting_case(
    consulting_case_id: str,
    website_url: str,
    max_pages: Optional[int] = None,
) -> list[CollectedSource]:
    """
    Fetch the homepage and a bounded set of likely-relevant internal pages
    for one consulting case, saving each as a CollectedSource.

    Always returns at least one CollectedSource (the homepage attempt,
    even if it failed) so the caller always has a record of what was
    tried.
    """
    max_pages = max_pages if max_pages is not None else settings.website_collector_max_pages
    logger.info("Collecting website content for case=%s url=%s", consulting_case_id, website_url)

    homepage_html, homepage_error = _fetch_page_html(website_url)
    if homepage_html is None:
        logger.warning("Homepage fetch failed for %s: %s", website_url, homepage_error)
        failed_source = create_and_save_collected_source(
            consulting_case_id=consulting_case_id,
            source_type=InformationSourceType.COMPANY_WEBSITE,
            source_url_or_path=website_url,
            raw_content="",
            collection_successful=False,
            collection_error_message=homepage_error,
        )
        return [failed_source]

    collected_sources: list[CollectedSource] = [
        create_and_save_collected_source(
            consulting_case_id=consulting_case_id,
            source_type=InformationSourceType.COMPANY_WEBSITE,
            source_url_or_path=website_url,
            raw_content=_extract_visible_text_from_html(homepage_html),
            collection_successful=True,
        )
    ]

    candidate_page_urls = _discover_candidate_page_urls(
        homepage_url=website_url,
        homepage_html=homepage_html,
        max_candidate_pages=max(max_pages - 1, 0),
    )

    for page_url in candidate_page_urls:
        time.sleep(settings.website_collector_polite_delay_seconds)
        page_html, page_error = _fetch_page_html(page_url)

        if page_html is None:
            logger.info("Skipping page (fetch failed) %s: %s", page_url, page_error)
            collected_sources.append(
                create_and_save_collected_source(
                    consulting_case_id=consulting_case_id,
                    source_type=InformationSourceType.COMPANY_WEBSITE,
                    source_url_or_path=page_url,
                    raw_content="",
                    collection_successful=False,
                    collection_error_message=page_error,
                )
            )
            continue

        collected_sources.append(
            create_and_save_collected_source(
                consulting_case_id=consulting_case_id,
                source_type=InformationSourceType.COMPANY_WEBSITE,
                source_url_or_path=page_url,
                raw_content=_extract_visible_text_from_html(page_html),
                collection_successful=True,
            )
        )

    logger.info(
        "Website collection complete for case=%s: %d page(s) attempted",
        consulting_case_id,
        len(collected_sources),
    )
    return collected_sources


def _fetch_page_html(url: str) -> tuple[Optional[str], Optional[str]]:
    """
    Fetch one URL. Returns (html, None) on success or (None, error_message)
    on any failure (network error, non-2xx status, non-HTML content type).
    """
    try:
        response = requests.get(
            url,
            headers={"User-Agent": settings.website_collector_user_agent},
            timeout=settings.website_collector_timeout_seconds,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as error:
        return None, str(error)

    content_type = response.headers.get("Content-Type", "")
    if not any(marker in content_type for marker in _HTML_CONTENT_TYPE_MARKERS):
        return None, f"Unsupported content type: {content_type or 'unknown'}"

    return response.text, None


def _extract_visible_text_from_html(html: str) -> str:
    """
    Strip non-content markup (script/style/etc.) and return the page's
    visible text, one meaningful line per line.

    Deliberately does NOT strip navigation, headers, or footers — removing
    boilerplate content is the Information Extraction Service's job
    (Brick 7), not the collector's.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(_NON_CONTENT_TAGS):
        tag.decompose()

    raw_text = soup.get_text(separator="\n")
    meaningful_lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    return "\n".join(meaningful_lines)


def _discover_candidate_page_urls(
    homepage_url: str,
    homepage_html: str,
    max_candidate_pages: int,
) -> list[str]:
    """
    Find same-domain internal links on the homepage that look relevant
    (about/products/services/blog/contact/...), falling back to common
    guessed paths if the homepage's own links don't yield enough.
    """
    if max_candidate_pages <= 0:
        return []

    soup = BeautifulSoup(homepage_html, "lxml")
    homepage_netloc = urlparse(homepage_url).netloc
    normalized_homepage = homepage_url.rstrip("/")

    discovered: list[str] = []
    seen: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith("#") or href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue

        absolute_url = urljoin(homepage_url, href).split("#")[0].rstrip("/")
        parsed = urlparse(absolute_url)

        if parsed.netloc != homepage_netloc:
            continue
        if absolute_url == normalized_homepage or absolute_url in seen:
            continue

        link_text = anchor.get_text(" ", strip=True).lower()
        haystack = f"{parsed.path.lower()} {link_text}"
        if any(keyword in haystack for keyword in _RELEVANT_PAGE_KEYWORDS):
            discovered.append(absolute_url)
            seen.add(absolute_url)

        if len(discovered) >= max_candidate_pages:
            return discovered[:max_candidate_pages]

    for guessed_path in _COMMON_PAGE_PATH_GUESSES:
        if len(discovered) >= max_candidate_pages:
            break
        guessed_url = urljoin(homepage_url, guessed_path).rstrip("/")
        if guessed_url not in seen and guessed_url != normalized_homepage:
            discovered.append(guessed_url)
            seen.add(guessed_url)

    return discovered[:max_candidate_pages]
