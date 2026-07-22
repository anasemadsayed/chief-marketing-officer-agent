"""
Database schema for cmoAI V1.

Eight tables, matching the spec exactly:
consulting_cases, company_profiles, collected_sources,
extracted_company_information, market_research, business_diagnosis,
marketing_strategies, generated_reports.

Design notes:
- consulting_cases.id and collected_sources.id are generated ids (many
  collected sources can belong to one case).
- The other six tables use consulting_case_id as their PRIMARY KEY,
  since V1's flow produces exactly one profile, one extraction, one
  market research pass, one diagnosis, one strategy, and one report per
  case. Repositories therefore save with INSERT OR REPLACE.
- List/nested fields (e.g. additional_links, competitors, findings) are
  stored as JSON text columns rather than extra tables — keeps V1 simple
  while still storing structured, meaningful data as required.
"""

from __future__ import annotations

from storage.database_connection import open_database_connection

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS consulting_cases (
    id TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    status TEXT NOT NULL,
    website_url TEXT,
    pdf_file_path TEXT,
    linkedin_url TEXT,
    facebook_url TEXT,
    instagram_url TEXT,
    additional_links TEXT NOT NULL DEFAULT '[]',
    failure_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS company_profiles (
    consulting_case_id TEXT PRIMARY KEY REFERENCES consulting_cases(id) ON DELETE CASCADE,
    company_name TEXT NOT NULL,
    industry TEXT,
    short_description TEXT,
    website_url TEXT,
    linkedin_url TEXT,
    facebook_url TEXT,
    instagram_url TEXT,
    headquarters_location TEXT,
    founding_year INTEGER,
    estimated_company_size_range TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collected_sources (
    id TEXT PRIMARY KEY,
    consulting_case_id TEXT NOT NULL REFERENCES consulting_cases(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    source_url_or_path TEXT NOT NULL,
    raw_content TEXT NOT NULL DEFAULT '',
    collection_successful INTEGER NOT NULL DEFAULT 1,
    collection_error_message TEXT,
    collected_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_collected_sources_case_id
    ON collected_sources(consulting_case_id);

CREATE TABLE IF NOT EXISTS extracted_company_information (
    consulting_case_id TEXT PRIMARY KEY REFERENCES consulting_cases(id) ON DELETE CASCADE,
    company_description_summary TEXT NOT NULL DEFAULT '',
    products_and_services TEXT NOT NULL DEFAULT '[]',
    value_proposition TEXT NOT NULL DEFAULT '',
    unique_selling_points TEXT NOT NULL DEFAULT '[]',
    target_audience_signals TEXT NOT NULL DEFAULT '[]',
    pricing_information TEXT NOT NULL DEFAULT '[]',
    contact_information TEXT NOT NULL DEFAULT '[]',
    notable_content_snippets TEXT NOT NULL DEFAULT '[]',
    extracted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_research (
    consulting_case_id TEXT PRIMARY KEY REFERENCES consulting_cases(id) ON DELETE CASCADE,
    industry_overview TEXT NOT NULL DEFAULT '',
    competitors TEXT NOT NULL DEFAULT '[]',
    target_audience_characteristics TEXT NOT NULL DEFAULT '[]',
    market_trends TEXT NOT NULL DEFAULT '[]',
    additional_notes TEXT NOT NULL DEFAULT '[]',
    researched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS business_diagnosis (
    consulting_case_id TEXT PRIMARY KEY REFERENCES consulting_cases(id) ON DELETE CASCADE,
    decision TEXT NOT NULL,
    primary_bottleneck TEXT NOT NULL,
    reasoning_summary TEXT NOT NULL,
    supporting_findings TEXT NOT NULL DEFAULT '[]',
    confidence TEXT NOT NULL,
    diagnosed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS marketing_strategies (
    consulting_case_id TEXT PRIMARY KEY REFERENCES consulting_cases(id) ON DELETE CASCADE,
    generated_because TEXT NOT NULL,
    executive_summary TEXT NOT NULL,
    strategic_objectives TEXT NOT NULL DEFAULT '[]',
    recommended_channels TEXT NOT NULL DEFAULT '[]',
    key_initiatives TEXT NOT NULL DEFAULT '[]',
    supporting_findings TEXT NOT NULL DEFAULT '[]',
    override_warning_message TEXT,
    generated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS generated_reports (
    consulting_case_id TEXT PRIMARY KEY REFERENCES consulting_cases(id) ON DELETE CASCADE,
    report_type TEXT NOT NULL,
    powerpoint_file_path TEXT,
    generated_at TEXT NOT NULL
);
"""


def initialize_database_schema() -> None:
    """Create all tables/indexes if they don't already exist. Safe to call repeatedly."""
    with open_database_connection() as connection:
        connection.executescript(CREATE_TABLES_SQL)
