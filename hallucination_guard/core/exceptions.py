"""Custom exception classes for HallucinationGuard validation pipeline.

This module provides clear, structured exceptions for different failure modes
in the validation system. Exceptions include attributes for programmatic
handling rather than string parsing.

All exceptions in this module:
- Inherit from HallucinationGuardError
- Provide structured attributes for error handling
- Include helpful error messages
- Support optional chaining via __cause__
"""

from typing import Optional


class HallucinationGuardError(Exception):
    """Base exception for all HallucinationGuard errors.

    This is the root exception class for all HallucinationGuard-specific
    errors. Users can catch this to handle any SDK error generically.

    Example:
        >>> try:
        ...     guard = Guard(policy="invalid_policy")
        ... except HallucinationGuardError as e:
        ...     print(f"SDK error: {e}")
    """

    pass


class HallucinationBlockedError(HallucinationGuardError):
    """Raised when output is blocked by the validation pipeline.

    This exception signals that the generated output failed validation and
    should not be returned to the user. It includes decision metadata for
    programmatic handling and user-facing error messages.

    Attributes:
        evidence: Human-readable explanation of why the output was blocked
        risk_score: Risk score [0.0, 1.0] where 1.0 = maximum risk
        decision: The validation decision (typically "block", but can be
                  "regenerate" or "abstain" in some policies)

    Example:
        >>> try:
        ...     decision = guard.validate(prompt, output, context)
        ...     if decision.decision == "block":
        ...         raise HallucinationBlockedError(
        ...             evidence=decision.evidence,
        ...             risk_score=decision.risk_score,
        ...             decision=decision.decision
        ...         )
        ... except HallucinationBlockedError as e:
        ...     print(f"Blocked (risk={e.risk_score:.2f}): {e.evidence}")
    """

    def __init__(
        self,
        evidence: str,
        risk_score: float,
        decision: str = "block",
        message: Optional[str] = None,
    ) -> None:
        """Initialize HallucinationBlockedError.

        Args:
            evidence: Human-readable explanation of the block
            risk_score: Risk score in [0.0, 1.0]
            decision: Validation decision ("block", "regenerate", "abstain")
            message: Optional custom error message (defaults to "Output blocked
                     by validation")
        """
        self.evidence = evidence
        self.risk_score = risk_score
        self.decision = decision

        if message is None:
            message = f"Output blocked by validation (risk={risk_score:.2f})"

        super().__init__(message)


class ValidationTimeoutError(HallucinationGuardError):
    """Raised when validation exceeds the configured latency budget.

    This exception indicates that the validation pipeline took longer than
    the configured timeout. It includes timing information for monitoring
    and debugging performance regressions.

    Attributes:
        latency_ms: Actual validation time in milliseconds
        budget_ms: Configured latency budget in milliseconds
        message: Error message with timing details

    Example:
        >>> try:
        ...     decision = guard.validate(prompt, output, context)
        ...     if decision.decision == "block" and decision.latency_ms > 100:
        ...         raise ValidationTimeoutError(
        ...             latency_ms=decision.latency_ms,
        ...             budget_ms=100
        ...         )
        ... except ValidationTimeoutError as e:
        ...     print(f"Validation too slow: {e.latency_ms}ms > {e.budget_ms}ms")
    """

    def __init__(
        self,
        latency_ms: float,
        budget_ms: float,
        message: Optional[str] = None,
    ) -> None:
        """Initialize ValidationTimeoutError.

        Args:
            latency_ms: Actual validation latency in milliseconds
            budget_ms: Configured latency budget in milliseconds
            message: Optional custom error message
        """
        self.latency_ms = latency_ms
        self.budget_ms = budget_ms

        if message is None:
            message = (
                f"Validation exceeded latency budget: "
                f"{latency_ms:.2f}ms > {budget_ms}ms"
            )

        super().__init__(message)


class PolicyLoadError(HallucinationGuardError):
    """Raised when a policy cannot be loaded or validated.

    This exception signals that the policy configuration is invalid,
    unreachable, or fails schema validation. It includes structured
    information about the failure for debugging.

    Attributes:
        policy_name: Name or path of the policy that failed to load
        reason: Human-readable explanation of the failure

    Example:
        >>> try:
        ...     guard = Guard(policy="nonexistent_policy")
        ... except PolicyLoadError as e:
        ...     print(f"Failed to load policy '{e.policy_name}': {e.reason}")
    """

    def __init__(
        self,
        policy_name: str,
        reason: str,
        message: Optional[str] = None,
    ) -> None:
        """Initialize PolicyLoadError.

        Args:
            policy_name: Name or path of the policy that failed
            reason: Human-readable explanation of the failure
            message: Optional custom error message
        """
        self.policy_name = policy_name
        self.reason = reason

        if message is None:
            message = f"Failed to load policy '{policy_name}': {reason}"

        super().__init__(message)
