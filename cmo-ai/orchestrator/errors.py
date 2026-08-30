"""
Shared exception types for the orchestrator package.
"""

from __future__ import annotations


class OrchestratorError(RuntimeError):
    """
    Raised when the orchestrator cannot produce a reliable result
    (diagnosis, strategy, or report).

    Unlike the non-reasoning services in Bricks 4-7, the orchestrator
    does NOT fabricate a plausible-looking fallback when something goes
    wrong — inventing a diagnosis would be actively harmful, not just
    unhelpful. Callers should catch this and mark the consulting case as
    FAILED (ConsultingCaseStatus.FAILED) with the error message as
    `failure_reason`, rather than silently proceeding with bad data.
    """
