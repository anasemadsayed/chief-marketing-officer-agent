"""
Logging configuration for the whole application.

Call `configure_application_logging()` once, as early as possible (e.g. at
the top of `main.py` or the API entrypoint). Every other module should then
simply do:

    import logging
    logger = logging.getLogger(__name__)

and logging will already be wired to both the console and a rotating log
file under the directory defined by `settings.log_dir`.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from config.settings import settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_MAX_LOG_FILE_BYTES = 5 * 1024 * 1024  # 5 MB per file
_BACKUP_LOG_FILE_COUNT = 5

_already_configured = False


def configure_application_logging() -> None:
    """
    Set up root logger handlers (console + rotating file) exactly once.

    Safe to call multiple times; subsequent calls are no-ops so importing
    this in several entrypoints (main.py, tests, api) never duplicates
    handlers or log lines.
    """
    global _already_configured
    if _already_configured:
        return

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.log_level)

    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    log_file_path = settings.log_directory_path / "cmoai.log"
    file_handler = RotatingFileHandler(
        filename=log_file_path,
        maxBytes=_MAX_LOG_FILE_BYTES,
        backupCount=_BACKUP_LOG_FILE_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Third-party libraries tend to be noisy at INFO/DEBUG — keep them quiet
    # unless the whole app is explicitly running in DEBUG mode.
    if settings.log_level != "DEBUG":
        for noisy_logger_name in ("httpx", "httpcore", "urllib3"):
            logging.getLogger(noisy_logger_name).setLevel(logging.WARNING)

    _already_configured = True
