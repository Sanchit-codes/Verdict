"""
HallucinationGuard SDK - Vendor-neutral AI hallucination prevention through inline validation.

Core exports:
    Guard: Main validation API
    GuardDecision: Validation decision result
    HallucinationBlockedError: Raised when output is blocked
    ValidationTimeoutError: Raised when validation exceeds budget
    PolicyLoadError: Raised when policy cannot be loaded
"""

__version__ = "0.1.0"

from hallucination_guard.core.guard import Guard
from hallucination_guard.core.decision import GuardDecision
from hallucination_guard.core.exceptions import (
    HallucinationBlockedError,
    HallucinationGuardError,
    PolicyLoadError,
    ValidationTimeoutError,
)

__all__ = [
    "__version__",
    "Guard",
    "GuardDecision",
    "HallucinationBlockedError",
    "HallucinationGuardError",
    "PolicyLoadError",
    "ValidationTimeoutError",
]
