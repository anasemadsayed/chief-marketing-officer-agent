"""
api
===

HTTP entrypoint for cmoAI (built in a later brick).

Exposes the main consulting flow (create case, run analysis, fetch
diagnosis/strategy/report) to a frontend or GUI. Contains no business
logic itself — it only translates HTTP requests into orchestrator calls
and returns domain objects as JSON.
"""
