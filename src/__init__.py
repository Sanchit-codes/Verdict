"""
HallucinationGuard SDK - Vendor-neutral AI hallucination prevention through inline validation.

Core exports:
    Guard: Main validation API
    GuardDecision: Validation decision result
    ActionEnforcementResult: ArmorIQ enforcement result attached to GuardDecision
    HallucinationBlockedError: Raised when output is blocked
    IntentViolationError: Raised when an action violates declared intent
    ValidationTimeoutError: Raised when validation exceeds budget
    PolicyLoadError: Raised when policy cannot be loaded
"""

__version__ = "0.1.0"

from verdict.core.guard import Guard
from verdict.core.decision import ActionEnforcementResult, GuardDecision
from verdict.core.exceptions import (
    HallucinationBlockedError,
    HallucinationGuardError,
    IntentViolationError,
    PolicyLoadError,
    ValidationTimeoutError,
)

__all__ = [
    "__version__",
    "Guard",
    "GuardDecision",
    "ActionEnforcementResult",
    "HallucinationBlockedError",
    "HallucinationGuardError",
    "IntentViolationError",
    "PolicyLoadError",
    "ValidationTimeoutError",
]
