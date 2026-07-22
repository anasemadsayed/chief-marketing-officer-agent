"""Shared pytest fixtures for the test suite."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from config.settings import settings
from storage.schema import initialize_database_schema


@pytest.fixture()
def isolated_test_database():
    """
    Point the shared `settings` object at a fresh temporary SQLite file
    for the duration of one test, then restore the original path.

    This keeps storage tests from ever touching a developer's real
    ./data/cmoai.db.
    """
    original_db_path = settings.sqlite_db_path
    with tempfile.TemporaryDirectory() as temp_dir:
        settings.sqlite_db_path = str(Path(temp_dir) / "test_cmoai.db")
        initialize_database_schema()
        yield
    settings.sqlite_db_path = original_db_path
