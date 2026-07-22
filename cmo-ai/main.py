"""
cmoAI — Local entrypoint.

Brick 1 scope: this script only proves that the project skeleton is wired
correctly — settings load from .env, logging works, and the folder
structure is importable. It intentionally contains no business logic yet.

Run with:
    python main.py
"""

import logging

from config.logging_config import configure_application_logging
from config.settings import settings
from storage import initialize_database_schema


def verify_project_skeleton_is_configured_correctly() -> None:
    """Sanity-check settings, logging, and database schema wiring."""
    configure_application_logging()
    logger = logging.getLogger(__name__)

    logger.info("cmoAI skeleton starting up")
    logger.info("Environment: %s", settings.app_env)
    logger.info("Main LLM provider: %s (model=%s)",
                 settings.main_llm_provider,
                 settings.gemini_model if settings.main_llm_provider == "gemini" else settings.nemotron_model)
    logger.info("Small LLM provider: %s (model=%s)",
                 settings.small_llm_provider, settings.small_llm_model)
    logger.info("SQLite database path: %s", settings.sqlite_db_full_path)
    logger.info("Log directory: %s", settings.log_directory_path)

    initialize_database_schema()
    logger.info("Database schema initialized (8 tables ready)")

    if not settings.get_main_reasoning_model_api_key():
        logger.warning(
            "No API key set for main LLM provider '%s'. "
            "Add it to your .env file before building later bricks.",
            settings.main_llm_provider,
        )

    logger.info("cmoAI skeleton is configured correctly ✅")


if __name__ == "__main__":
    verify_project_skeleton_is_configured_correctly()
