"""
PDF Collector Service.

Pure collection: given a local PDF file path, extracts whatever text
layer the file already has and stores it as a raw CollectedSource.

Out of scope for V1: OCR of scanned/image-only PDFs. If a PDF has no
text layer, that is stored honestly as an empty (but successful)
collection result rather than pretending nothing was tried.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pypdf import PdfReader

from config.settings import settings
from domain import CollectedSource, InformationSourceType
from storage.collected_source_repository import create_and_save_collected_source

logger = logging.getLogger(__name__)


def collect_pdf_content_for_consulting_case(consulting_case_id: str, pdf_file_path: str) -> CollectedSource:
    """
    Extract text from a locally available PDF file and save it as a
    CollectedSource.

    On any failure — missing file, corrupted PDF, or a PDF that requires
    a password we don't have — a CollectedSource is still saved with
    collection_successful=False and an explanatory error message, the
    same pattern used by the website and social media collectors.
    """
    logger.info("Collecting PDF content for case=%s path=%s", consulting_case_id, pdf_file_path)

    path = Path(pdf_file_path)
    if not path.is_file():
        error_message = f"PDF file not found: {pdf_file_path}"
        logger.warning(error_message)
        return _save_failed_pdf_source(consulting_case_id, pdf_file_path, error_message)

    try:
        reader = PdfReader(str(path))
    except Exception as error:  # pypdf can raise several distinct error types on corrupted input
        error_message = f"Failed to open PDF: {error}"
        logger.warning("Failed to open PDF %s: %s", pdf_file_path, error)
        return _save_failed_pdf_source(consulting_case_id, pdf_file_path, error_message)

    if reader.is_encrypted:
        try:
            decrypt_result = reader.decrypt("")
        except Exception as error:
            decrypt_result = 0
            logger.debug("Decrypt attempt raised for %s: %s", pdf_file_path, error)

        if not decrypt_result:
            error_message = "PDF is password-protected and could not be opened"
            logger.warning("%s: %s", error_message, pdf_file_path)
            return _save_failed_pdf_source(consulting_case_id, pdf_file_path, error_message)

    total_pages = len(reader.pages)
    pages_to_process = reader.pages[: settings.pdf_collector_max_pages_to_process]
    if total_pages > settings.pdf_collector_max_pages_to_process:
        logger.warning(
            "PDF %s has %d pages; only processing the first %d",
            pdf_file_path, total_pages, settings.pdf_collector_max_pages_to_process,
        )

    extracted_page_texts: list[str] = []
    for page_number, page in enumerate(pages_to_process, start=1):
        try:
            page_text = page.extract_text() or ""
        except Exception as error:  # one malformed page shouldn't fail the whole document
            logger.debug("Failed to extract text from page %d of %s: %s", page_number, pdf_file_path, error)
            page_text = ""
        extracted_page_texts.append(page_text)

    raw_content = "\n\n".join(text.strip() for text in extracted_page_texts if text.strip())

    if not raw_content:
        logger.info(
            "PDF %s opened successfully but no extractable text was found "
            "(it may be a scanned/image-only document; OCR is not supported in V1)",
            pdf_file_path,
        )

    return create_and_save_collected_source(
        consulting_case_id=consulting_case_id,
        source_type=InformationSourceType.UPLOADED_PDF,
        source_url_or_path=pdf_file_path,
        raw_content=raw_content,
        collection_successful=True,
    )


def _save_failed_pdf_source(
    consulting_case_id: str, pdf_file_path: str, error_message: str
) -> CollectedSource:
    return create_and_save_collected_source(
        consulting_case_id=consulting_case_id,
        source_type=InformationSourceType.UPLOADED_PDF,
        source_url_or_path=pdf_file_path,
        raw_content="",
        collection_successful=False,
        collection_error_message=error_message,
    )
