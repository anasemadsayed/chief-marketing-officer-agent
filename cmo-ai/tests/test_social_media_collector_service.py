"""
Tests for the Social Media Collector Service (Brick 5, Phase 2).

Network calls are never made in these tests — `requests.get` is never
hit. `_fetch_profile_page_html` is monkeypatched with canned HTML so no
real HTTP request occurs, matching the pattern used for the website
collector's tests.
"""

from __future__ import annotations

from domain import InformationSourceType
from services import social_media_collector_service as collector
from storage.collected_source_repository import list_collected_sources_for_case
from storage.consulting_case_repository import create_consulting_case

SAMPLE_LINKEDIN_HTML = """
<html>
  <head>
    <title>Acme Corp | LinkedIn</title>
    <meta property="og:title" content="Acme Corp">
    <meta property="og:site_name" content="LinkedIn">
    <meta property="og:description" content="Acme Corp builds project management software. 5,201 followers.">
    <script>window.__state = {huge: "blob"};</script>
  </head>
  <body>
    <div class="login-wall">
      <h1>Sign in to see more</h1>
      <p>Join LinkedIn to view Acme Corp's full profile.</p>
    </div>
  </body>
</html>
"""

SAMPLE_FACEBOOK_HTML = """
<html>
  <head>
    <meta name="twitter:title" content="Acme Corp">
    <meta name="twitter:description" content="Official Facebook page of Acme Corp.">
  </head>
  <body><p>Log in to Facebook to see posts from Acme Corp.</p></body>
</html>
"""

SAMPLE_BARE_HTML_NO_META = """
<html><head><title>Just A Title</title></head><body><p>Some plain text.</p></body></html>
"""


def test_extract_preview_meta_lines_prefers_open_graph():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(SAMPLE_LINKEDIN_HTML, "lxml")
    lines = collector._extract_preview_meta_lines(soup)

    assert "Title: Acme Corp" in lines
    assert "Site Name: LinkedIn" in lines
    assert any("5,201 followers" in line for line in lines)


def test_extract_preview_meta_lines_falls_back_to_twitter_card():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(SAMPLE_FACEBOOK_HTML, "lxml")
    lines = collector._extract_preview_meta_lines(soup)

    assert "Title (Twitter Card): Acme Corp" in lines
    assert any("Official Facebook page" in line for line in lines)


def test_extract_preview_meta_lines_falls_back_to_page_title_when_no_meta():
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(SAMPLE_BARE_HTML_NO_META, "lxml")
    lines = collector._extract_preview_meta_lines(soup)

    assert lines == ["Page Title: Just A Title"]


def test_build_profile_raw_content_strips_scripts_but_keeps_login_wall_text():
    content = collector._build_profile_raw_content(SAMPLE_LINKEDIN_HTML)

    assert "window.__state" not in content
    assert "huge" not in content
    assert "Title: Acme Corp" in content
    # Login-wall text is intentionally preserved — cleaning it out is Brick 7's job.
    assert "Sign in to see more" in content


def test_collect_social_media_profile_content_saves_successful_result(isolated_test_database, monkeypatch):
    case = create_consulting_case(company_name="Acme Corp")

    monkeypatch.setattr(collector, "_fetch_profile_page_html", lambda url: (SAMPLE_LINKEDIN_HTML, None))

    result = collector.collect_social_media_profile_content(
        consulting_case_id=case.id,
        platform=InformationSourceType.LINKEDIN_PROFILE,
        profile_url="https://linkedin.com/company/acme",
    )

    assert result.collection_successful is True
    assert result.source_type == InformationSourceType.LINKEDIN_PROFILE
    assert "Acme Corp" in result.raw_content

    persisted = list_collected_sources_for_case(case.id)
    assert len(persisted) == 1


def test_collect_social_media_profile_content_handles_fetch_failure_gracefully(isolated_test_database, monkeypatch):
    case = create_consulting_case(company_name="Blocked Co")

    monkeypatch.setattr(
        collector, "_fetch_profile_page_html", lambda url: (None, "403 Client Error: Forbidden")
    )

    result = collector.collect_social_media_profile_content(
        consulting_case_id=case.id,
        platform=InformationSourceType.INSTAGRAM_PROFILE,
        profile_url="https://instagram.com/acmecorp",
    )

    assert result.collection_successful is False
    assert result.raw_content == ""
    assert "403" in result.collection_error_message


def test_collect_social_media_profiles_for_consulting_case_only_attempts_provided_urls(
    isolated_test_database, monkeypatch
):
    case = create_consulting_case(company_name="Acme Corp")

    attempted_platforms: list[InformationSourceType] = []

    def fake_collect(consulting_case_id, platform, profile_url):
        attempted_platforms.append(platform)
        return collector.create_and_save_collected_source(
            consulting_case_id=consulting_case_id,
            source_type=platform,
            source_url_or_path=profile_url,
            raw_content="stub",
            collection_successful=True,
        )

    monkeypatch.setattr(collector, "collect_social_media_profile_content", fake_collect)

    results = collector.collect_social_media_profiles_for_consulting_case(
        consulting_case_id=case.id,
        linkedin_url="https://linkedin.com/company/acme",
        facebook_url=None,
        instagram_url="https://instagram.com/acmecorp",
    )

    assert len(results) == 2
    assert InformationSourceType.LINKEDIN_PROFILE in attempted_platforms
    assert InformationSourceType.INSTAGRAM_PROFILE in attempted_platforms
    assert InformationSourceType.FACEBOOK_PROFILE not in attempted_platforms


def test_collect_social_media_profiles_returns_empty_list_when_no_urls_provided(isolated_test_database):
    case = create_consulting_case(company_name="No Socials Co")

    results = collector.collect_social_media_profiles_for_consulting_case(consulting_case_id=case.id)

    assert results == []
