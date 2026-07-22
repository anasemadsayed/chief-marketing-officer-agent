"""
SQLite connection management.

This is the only module allowed to open a raw `sqlite3.Connection`.
Every repository goes through `open_database_connection()` so
transaction handling (commit on success, rollback on error) stays
consistent everywhere.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from config.settings import settings


def get_database_connection() -> sqlite3.Connection:
    """Open a new connection to the configured SQLite database file."""
    connection = sqlite3.connect(settings.sqlite_db_full_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def open_database_connection() -> Iterator[sqlite3.Connection]:
    """
    Context manager that opens a connection, commits on success, rolls
    back on any exception, and always closes the connection.

    Usage:
        with open_database_connection() as connection:
            connection.execute(...)
    """
    connection = get_database_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
