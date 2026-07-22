"""
Small serialization helpers shared by every repository.

Keeps the JSON-encoding of list/nested-model fields, and URL-to-string
conversion, consistent across all eight tables instead of repeated
inline in each repository file.
"""

from __future__ import annotations

import json
from typing import Optional, Type, TypeVar

from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


def serialize_model_list_to_json(models: list[BaseModel]) -> str:
    """Turn a list of Pydantic models into a JSON string for storage."""
    return json.dumps([model.model_dump(mode="json") for model in models])


def deserialize_json_to_model_list(raw: Optional[str], model_cls: Type[ModelT]) -> list[ModelT]:
    """Turn a stored JSON string back into a list of Pydantic models."""
    if not raw:
        return []
    return [model_cls.model_validate(item) for item in json.loads(raw)]


def serialize_string_list_to_json(items: list[str]) -> str:
    """Turn a list of plain strings into a JSON string for storage."""
    return json.dumps(items)


def deserialize_json_to_string_list(raw: Optional[str]) -> list[str]:
    """Turn a stored JSON string back into a list of plain strings."""
    if not raw:
        return []
    return json.loads(raw)


def url_or_none_to_str(value: object) -> Optional[str]:
    """Convert a pydantic HttpUrl (or None) into a plain string (or None) for storage."""
    return str(value) if value is not None else None
