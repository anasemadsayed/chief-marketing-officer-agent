"""
domain
======

Pure data models for cmoAI (Pydantic models / dataclasses only).

This package defines the shared vocabulary of the whole system:
CompanyProfile, CollectedSource, ExtractedCompanyInformation,
MarketResearch, Finding, BusinessDiagnosis, MarketingStrategy,
ConsultingCase, GeneratedReport, etc.

Rules for this package:
- No business logic.
- No I/O (no HTTP calls, no database calls, no file reads).
- No LLM calls.
- Only typed data structures and their validation rules.

Every service and the orchestrator communicate exclusively through
these models.
"""
