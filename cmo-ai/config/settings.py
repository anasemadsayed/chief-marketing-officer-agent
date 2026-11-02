"""
Central application configuration.

All environment-dependent values (API keys, model names, paths, log level,
etc.) are read once here and exposed through a single `settings` object.
No other module should call `os.getenv(...)` directly — everything goes
through this file so there is exactly one source of truth for configuration.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class ApplicationSettings(BaseSettings):
    """
    Typed, validated application settings.

    Values are loaded from environment variables and/or a local ".env" file
    in the project root. See ".env.example" for the full list of supported
    variables and their meaning.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -- Main reasoning model (Orchestrator) ---------------------------------
    main_llm_provider: Literal["gemini", "nemotron"] = "gemini"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    nvidia_api_key: str = ""
    nemotron_model: str = "nvidia/nemotron-4-340b-instruct"

    # -- Small model (Market Research + Information Extraction services) ----
    small_llm_provider: Literal["gemini", "nemotron"] = "gemini"
    small_llm_model: str = "gemini-2.0-flash-lite"

    # -- Database -------------------------------------------------------------
    sqlite_db_path: str = "./data/cmoai.db"

    # -- Application ------------------------------------------------------------
    app_env: Literal["development", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_dir: str = "./logs"

    # -- API layer --------------------------------------------------------------
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # -- Website Collector Service ------------------------------------------
    website_collector_timeout_seconds: int = 15
    website_collector_max_pages: int = 8
    website_collector_user_agent: str = "Mozilla/5.0 (compatible; cmoAI-WebsiteCollector/1.0)"
    website_collector_polite_delay_seconds: float = 0.5

    # -- PDF Collector Service ------------------------------------------------
    pdf_collector_max_pages_to_process: int = 100

    # -- Social Media Collector Service ----------------------------------------
    social_media_collector_timeout_seconds: int = 15
    social_media_collector_user_agent: str = "Mozilla/5.0 (compatible; cmoAI-SocialMediaCollector/1.0)"

    # -- Agent-Reach & OpenCLI Integration -------------------------------------
    # When enabled, the social media collector will try Agent-Reach's tool
    # ecosystem (Jina Reader, opencli, mcporter) first, falling back to the
    # basic OG-meta-tag scraper if Agent-Reach is not installed or fails.
    agent_reach_enabled: bool = True
    agent_reach_timeout_seconds: int = 45
    opencli_binary_path: str = "/home/nas_mousa/.nvm/versions/node/v22.23.3/bin/opencli"
    node_binary_dir: str = "/home/nas_mousa/.nvm/versions/node/v22.23.3/bin"

    # -- Market Research Service ------------------------------------------------
    market_research_max_context_characters: int = 15000
    market_research_llm_temperature: float = 0.3
    market_research_use_web_search: bool = True

    # -- Information Extraction Service ------------------------------------------
    information_extraction_max_context_characters: int = 25000
    information_extraction_llm_temperature: float = 0.2

    # -- Orchestrator: Diagnosis --------------------------------------------------
    diagnosis_llm_temperature: float = 0.4
    diagnosis_llm_max_output_tokens: int = 3000

    # -- Orchestrator: Marketing Strategy ------------------------------------------
    strategy_llm_temperature: float = 0.5
    strategy_llm_max_output_tokens: int = 3500

    # -- PowerPoint Generator Service ------------------------------------------
    powerpoint_output_directory: str = "./data/generated_reports"

    @property
    def sqlite_db_full_path(self) -> Path:
        """Absolute path to the SQLite database file, creating its parent dir."""
        path = Path(self.sqlite_db_path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def log_directory_path(self) -> Path:
        """Absolute path to the log directory, created if missing."""
        path = Path(self.log_dir).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def powerpoint_output_directory_path(self) -> Path:
        """Absolute path to the generated-PowerPoint output directory, created if missing."""
        path = Path(self.powerpoint_output_directory).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_main_reasoning_model_api_key(self) -> str:
        """Return the API key for whichever provider is configured as main."""
        if self.main_llm_provider == "gemini":
            return self.gemini_api_key
        return self.nvidia_api_key

    def get_small_model_api_key(self) -> str:
        """Return the API key for whichever provider is configured as small."""
        if self.small_llm_provider == "gemini":
            return self.gemini_api_key
        return self.nvidia_api_key


# Single shared instance imported everywhere else:
#   from config.settings import settings
settings = ApplicationSettings()
