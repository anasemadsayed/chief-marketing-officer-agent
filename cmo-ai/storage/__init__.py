"""
storage
=======

SQLite persistence layer.

Responsible for:
- schema creation for all consulting-case tables,
- mapping domain models to/from database rows (repository pattern),
- generating unique, readable consulting case identifiers.

No SQL should be written or executed anywhere outside this package.
"""
