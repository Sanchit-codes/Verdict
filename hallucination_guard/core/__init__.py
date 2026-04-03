"""Core validation engine components."""

from hallucination_guard.core.decision import (
    GuardDecision,
    aggregate_scores,
    make_decision,
    generate_suggested_fix,
)

__all__ = [
    "GuardDecision",
    "aggregate_scores",
    "make_decision",
    "generate_suggested_fix",
]
