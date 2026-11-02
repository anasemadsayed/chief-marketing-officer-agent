"""
Tests for the PDF Collector Service (Brick 5, Phase 1).

Uses real PDF fixtures (tests/fixtures/*.pdf) and real pypdf parsing —
no mocking of the PDF library itself, since PDF parsing correctness is
exactly what this service needs to get right.
"""

from __future__ import annotations

from pathlib import Path

from domain import InformationSourceType
from services.pdf_collector_service import collect_pdf_content_for_consulting_case
from storage.collected_source_repository import list_collected_sources_for_case
from storage.consulting_case_repository import create_consulting_case

FIXTURES_DIR = Path(__file__).parent / "fixtures"
VALID_PDF_PATH = str(FIXTURES_DIR / "sample_company_report.pdf")
ENCRYPTED_PDF_PATH = str(FIXTURES_DIR / "sample_encrypted_report.pdf")


def test_collect_pdf_content_extracts_text_from_valid_pdf(isolated_test_database):
    case = create_consulting_case(company_name="Acme Corp", pdf_file_path=VALID_PDF_PATH)

    result = collect_pdf_content_for_consulting_case(
        consulting_case_id=case.id, pdf_file_path=VALID_PDF_PATH
    )

    assert result.collection_successful is True
    assert result.source_type == InformationSourceType.UPLOADED_PDF
    assert result.collection_error_message is None
    assert "Acme Corp Annual Report" in result.raw_content
    assert "Pricing Overview" in result.raw_content

    persisted = list_collected_sources_for_case(case.id)
    assert len(persisted) == 1
    assert persisted[0].id == result.id


def test_collect_pdf_content_handles_missing_file(isolated_test_database):
    case = create_consulting_case(company_name="Ghost Co")

    result = collect_pdf_content_for_consulting_case(
        consulting_case_id=case.id, pdf_file_path="/nonexistent/path/report.pdf"
    )

    assert result.collection_successful is False
    assert result.raw_content == ""
    assert "not found" in result.collection_error_message.lower()


def test_collect_pdf_content_handles_corrupted_pdf(isolated_test_database, tmp_path):
    corrupted_path = tmp_path / "corrupted.pdf"
    corrupted_path.write_text("this is not a real pdf file, just garbage text 12345")

    case = create_consulting_case(company_name="Broken PDF Co")
    result = collect_pdf_content_for_consulting_case(
        consulting_case_id=case.id, pdf_file_path=str(corrupted_path)
    )

    assert result.collection_successful is False
    assert result.raw_content == ""
    assert result.collection_error_message is not None


def test_collect_pdf_content_handles_password_protected_pdf(isolated_test_database):
    case = create_consulting_case(company_name="Secretive Co", pdf_file_path=ENCRYPTED_PDF_PATH)

    result = collect_pdf_content_for_consulting_case(
        consulting_case_id=case.id, pdf_file_path=ENCRYPTED_PDF_PATH
    )

    assert result.collection_successful is False
    assert "password-protected" in result.collection_error_message.lower()


def test_collect_pdf_content_respects_max_pages_setting(isolated_test_database, monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "pdf_collector_max_pages_to_process", 1)

    case = create_consulting_case(company_name="Acme Corp", pdf_file_path=VALID_PDF_PATH)
    result = collect_pdf_content_for_consulting_case(
        consulting_case_id=case.id, pdf_file_path=VALID_PDF_PATH
    )

    assert result.collection_successful is True
    assert "Acme Corp Annual Report" in result.raw_content
    # Page 2 content must be excluded once the page cap is hit.
    assert "Pricing Overview" not in result.raw_content
