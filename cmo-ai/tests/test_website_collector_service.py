"""
Tests for the Website Collector Service (Brick 4).

Network calls are never made in these tests — `requests.get` is never hit.
Pure parsing functions (_extract_visible_text_from_html,
_discover_candidate_page_urls) are tested directly with canned HTML, and
the top-level orchestration function is tested by monkeypatching
`_fetch_page_html` so no real HTTP request occurs.
"""

from __future__ import annotations

from domain import InformationSourceType
from services import website_collector_service as collector
from storage.collected_source_repository import list_collected_sources_for_case
from storage.consulting_case_repository import create_consulting_case

SAMPLE_HOMEPAGE_HTML = """
<html>
  <head><title>Acme Corp</title>
    <style>body { color: red; }</style>
    <script>console.log("tracking pixel");</script>
  </head>
  <body>
    <nav>
      <a href="/about">About Us</a>
      <a href="/products">Our Products</a>
      <a href="/contact">Contact</a>
      <a href="https://external-site.example.com/partner">Partner Site</a>
      <a href="#top">Back to top</a>
      <a href="mailto:hello@acme.example.com">Email us</a>
    </nav>
    <main>
      <h1>Welcome to Acme Corp</h1>
      <p>We build project management software for growing teams.</p>
    </main>
  </body>
</html>
"""

SAMPLE_ABOUT_PAGE_HTML = """
<html><body>
  <h1>About Acme Corp</h1>
  <p>Founded in 2019, Acme Corp helps teams ship faster.</p>
</body></html>
"""


def test_extract_visible_text_strips_script_and_style_but_keeps_nav():
    text = collector._extract_visible_text_from_html(SAMPLE_HOMEPAGE_HTML)
    assert "console.log" not in text
    assert "color: red" not in text
    assert "Welcome to Acme Corp" in text
    # Nav text is intentionally preserved — cleaning it out is Brick 7's job.
    assert "About Us" in text


def test_discover_candidate_page_urls_finds_relevant_internal_links_only():
    urls = collector._discover_candidate_page_urls(
        homepage_url="https://acme.example.com",
        homepage_html=SAMPLE_HOMEPAGE_HTML,
        max_candidate_pages=5,
    )
    assert "https://acme.example.com/about" in urls
    assert "https://acme.example.com/products" in urls
    assert "https://acme.example.com/contact" in urls
    # External domain and non-page links must be excluded.
    assert not any("external-site.example.com" in url for url in urls)
    assert not any(url.startswith("mailto:") for url in urls)


def test_discover_candidate_page_urls_respects_max_candidate_pages():
    urls = collector._discover_candidate_page_urls(
        homepage_url="https://acme.example.com",
        homepage_html=SAMPLE_HOMEPAGE_HTML,
        max_candidate_pages=1,
    )
    assert len(urls) == 1


def test_discover_candidate_page_urls_falls_back_to_common_guesses_when_no_links():
    bare_html = "<html><body><p>No links here.</p></body></html>"
    urls = collector._discover_candidate_page_urls(
        homepage_url="https://acme.example.com",
        homepage_html=bare_html,
        max_candidate_pages=3,
    )
    assert len(urls) == 3
    assert all(url.startswith("https://acme.example.com/") for url in urls)


def test_collect_website_content_saves_homepage_and_discovered_pages(isolated_test_database, monkeypatch):
    case = create_consulting_case(company_name="Acme Corp", website_url="https://acme.example.com")

    def fake_fetch_page_html(url: str):
        if url.rstrip("/") == "https://acme.example.com":
            return SAMPLE_HOMEPAGE_HTML, None
        if url.rstrip("/") == "https://acme.example.com/about":
            return SAMPLE_ABOUT_PAGE_HTML, None
        return None, "404 Not Found"

    monkeypatch.setattr(collector, "_fetch_page_html", fake_fetch_page_html)
    monkeypatch.setattr(collector.time, "sleep", lambda _seconds: None)

    results = collector.collect_website_content_for_consulting_case(
        consulting_case_id=case.id,
        website_url="https://acme.example.com",
        max_pages=4,
    )

    assert len(results) >= 2
    homepage_result = next(r for r in results if r.source_url_or_path == "https://acme.example.com")
    assert homepage_result.collection_successful is True
    assert "Welcome to Acme Corp" in homepage_result.raw_content
    assert homepage_result.source_type == InformationSourceType.COMPANY_WEBSITE

    about_result = next(r for r in results if r.source_url_or_path == "https://acme.example.com/about")
    assert about_result.collection_successful is True
    assert "Founded in 2019" in about_result.raw_content

    # Every result must actually be persisted, not just returned in-memory.
    persisted = list_collected_sources_for_case(case.id)
    assert len(persisted) == len(results)


def test_collect_website_content_handles_unreachable_homepage_gracefully(isolated_test_database, monkeypatch):
    case = create_consulting_case(company_name="Broken Site Co", website_url="https://broken.example.com")

    def fake_fetch_page_html(url: str):
        return None, "Connection timed out"

    monkeypatch.setattr(collector, "_fetch_page_html", fake_fetch_page_html)

    results = collector.collect_website_content_for_consulting_case(
        consulting_case_id=case.id,
        website_url="https://broken.example.com",
    )

    assert len(results) == 1
    assert results[0].collection_successful is False
    assert results[0].collection_error_message == "Connection timed out"


def test_collect_website_content_records_failed_subpages_without_stopping(isolated_test_database, monkeypatch):
    case = create_consulting_case(company_name="Partial Co", website_url="https://partial.example.com")

    def fake_fetch_page_html(url: str):
        if url.rstrip("/") == "https://partial.example.com":
            return SAMPLE_HOMEPAGE_HTML, None
        return None, "500 Server Error"

    monkeypatch.setattr(collector, "_fetch_page_html", fake_fetch_page_html)
    monkeypatch.setattr(collector.time, "sleep", lambda _seconds: None)

    results = collector.collect_website_content_for_consulting_case(
        consulting_case_id=case.id,
        website_url="https://partial.example.com",
        max_pages=3,
    )

    homepage_result = results[0]
    assert homepage_result.collection_successful is True

    failed_subpages = [r for r in results[1:] if not r.collection_successful]
    assert len(failed_subpages) == len(results) - 1
    assert all(r.collection_error_message == "500 Server Error" for r in failed_subpages)
