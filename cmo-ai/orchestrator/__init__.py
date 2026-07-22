"""
orchestrator
============

The single intelligent decision-maker in the system.

The orchestrator is the only component allowed to:
- reason about the business,
- perform root-cause diagnosis,
- decide whether marketing is the correct solution,
- generate the marketing strategy,
- generate the final report.

It consumes only clean, structured domain objects that have already been
collected and extracted by the services package — it never touches raw
data or performs its own data collection.
"""
