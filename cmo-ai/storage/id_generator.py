"""
Unique, readable identifier generation.

Per the spec: the company name may be used to make the identifier
readable, but the final id must not depend on the company name alone —
a random suffix guarantees uniqueness even for two cases with the exact
same company name.
"""

from __future__ import annotations

import uuid

from slugify import slugify


def generate_unique_consulting_case_id(company_name: str) -> str:
    """
    Build a readable-but-unique consulting case id, e.g.:
        "acme-corp-4f9a21c8"

    Falls back to a generic slug if the company name produces an empty
    slug (e.g. a name made only of symbols/emoji).
    """
    base_slug = slugify(company_name) or "company"
    unique_suffix = uuid.uuid4().hex[:8]
    return f"{base_slug}-{unique_suffix}"


def generate_unique_record_id(prefix: str) -> str:
    """
    Generate a unique id for non-case records (e.g. collected sources),
    e.g. generate_unique_record_id("src") -> "src-1a2b3c4d5e6f".
    """
    return f"{prefix}-{uuid.uuid4().hex[:12]}"
