"""
config
======

Application-wide configuration and logging setup.

- settings.py         -> typed environment configuration (settings object)
- logging_config.py   -> console + rotating file logging setup

Every other package imports configuration from here rather than reading
environment variables directly.
"""
