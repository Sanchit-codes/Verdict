"""Main Guard class - public API entry point for HallucinationGuard validation.

This module provides the primary user-facing Guard class that wraps the
validation pipeline, decision engine, and trace export system. Guard is
designed to be simple to use while supporting advanced customization.

Typical usage:
    >>> from hallucination_guard import Guard
    >>>
    >>> guard = Guard(policy="rag_strict")
    >>> decision = guard.validate(
    ...     prompt="What is AI?",
    ...     output="AI is artificial intelligence...",
    ...     context="AI stands for artificial intelligence..."
    ... )
    >>> if decision.decision == "allow":
    ...     print(decision.output)
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional, Union

from hallucination_guard.core.decision import GuardDecision
from hallucination_guard.core.exceptions import PolicyLoadError
from hallucination_guard.core.pipeline import ValidationPipeline
from hallucination_guard.core.trace import GuardTrace, export_trace
from hallucination_guard.policy.loader import load_policy as _load_policy
from hallucination_guard.policy.schema import PolicyConfig
from hallucination_guard.validators.base import ValidationInput

logger = logging.getLogger(__name__)


class Guard:
    """Main validation API for HallucinationGuard.

    Guard is the entry point for text validation. It wraps the validation
    pipeline, decision engine, and optional trace export system. Guard
    handles policy loading, pipeline orchestration, and decision making.

    Attributes:
        policy: The loaded PolicyConfig governing validation behavior
        pipeline: The ValidationPipeline orchestrator
        trace_enabled: Whether to export traces after each validation

    Example:
        >>> guard = Guard(policy="default")
        >>> decision = guard.validate(prompt, output, context)
        >>> if decision.decision == "allow":
        ...     return decision.output
        >>> elif decision.decision == "block":
        ...     raise HallucinationBlockedError(decision.evidence)
    """

    def __init__(
        self,
        policy: Union[str, Path, PolicyConfig],
        trace_enabled: Optional[bool] = None,
    ) -> None:
        """Initialize Guard with a policy configuration.

        Loads the specified policy (by name, file path, or PolicyConfig object),
        validates it, and initializes the validation pipeline. Trace export is
        automatically enabled if LANGFUSE_PUBLIC_KEY environment variable is set
        and trace_enabled is not explicitly False.

        Args:
            policy: One of:
                - Policy name (str): "default", "rag_strict", "chatbot"
                - File path (str/Path): "/path/to/custom_policy.yaml"
                - PolicyConfig object: Pre-loaded configuration
            trace_enabled: Whether to export traces. If None (default), auto-enables
                          if LANGFUSE_PUBLIC_KEY is set. Explicit True/False overrides.

        Raises:
            PolicyLoadError: If policy cannot be loaded or validated
            ValueError: If policy argument type is invalid

        Example:
            >>> # By name
            >>> guard1 = Guard(policy="default")
            >>>
            >>> # By file path
            >>> guard2 = Guard(policy="./custom_policy.yaml")
            >>>
            >>> # By PolicyConfig
            >>> config = load_policy("rag_strict")
            >>> guard3 = Guard(policy=config)
        """
        # Load policy
        try:
            if isinstance(policy, PolicyConfig):
                self.policy = policy
            elif isinstance(policy, (str, Path)):
                self.policy = _load_policy(str(policy))
            else:
                raise ValueError(
                    f"policy must be str, Path, or PolicyConfig, got {type(policy)}"
                )
        except Exception as e:
            # Wrap any policy loading errors in PolicyLoadError
            if isinstance(e, PolicyLoadError):
                raise
            policy_name = policy.name if isinstance(policy, PolicyConfig) else str(policy)
            raise PolicyLoadError(
                policy_name=policy_name,
                reason=str(e),
            ) from e

        # Initialize pipeline with loaded policy
        self.pipeline = ValidationPipeline(self.policy)

        # Determine trace settings
        if trace_enabled is None:
            # Auto-enable if Langfuse credentials are set
            langfuse_key = os.getenv("LANGFUSE_PUBLIC_KEY")
            self.trace_enabled = langfuse_key is not None
        else:
            self.trace_enabled = trace_enabled

        logger.debug(
            f"Guard initialized with policy '{self.policy.name}' "
            f"(trace_enabled={self.trace_enabled})"
        )

    def validate(
        self,
        prompt: str,
        output: str,
        context: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> GuardDecision:
        """Validate model output synchronously.

        Runs the three-tier validation pipeline and returns a structured decision.
        Does NOT auto-raise exceptions—users check decision.decision field and
        raise exceptions manually if desired.

        Trace export happens automatically if trace_enabled=True, with all errors
        gracefully logged and never propagated.

        Args:
            prompt: User prompt or query that triggered the generation
            output: Model-generated text to validate
            context: Optional reference context (e.g., retrieved documents)
            domain: Optional domain metadata (e.g., "healthcare", "finance")

        Returns:
            GuardDecision with:
            - decision: "allow", "block", "regenerate", or "abstain"
            - risk_score: Calculated risk in [0.0, 1.0]
            - confidence: Confidence in decision based on validator agreement
            - evidence: Human-readable explanation
            - validator_results: Individual results from each validator
            - latency_ms: Total validation time

        Raises:
            ValueError: If prompt or output are empty strings
            PolicyLoadError: Only if policy was invalid at initialization

        Note:
            - Does NOT raise exceptions for validation failures
            - Users should check decision.decision and handle accordingly
            - Trace export failures are logged as warnings, never raised

        Example:
            >>> decision = guard.validate(prompt, output, context)
            >>> if decision.decision == "allow":
            ...     return decision.output
            >>> elif decision.decision == "block":
            ...     raise HallucinationBlockedError(decision.evidence)
            >>> elif decision.decision == "regenerate":
            ...     return await retry_with_hint(decision.suggested_fix)
        """
        if not prompt or not isinstance(prompt, str):
            raise ValueError("prompt must be a non-empty string")
        if not output or not isinstance(output, str):
            raise ValueError("output must be a non-empty string")

        # Build validation input
        validation_input = ValidationInput(
            prompt=prompt,
            output=output,
            context=context,
            domain=domain,
        )

        # Run pipeline
        decision = self.pipeline.run(validation_input)

        # Export trace if enabled (with graceful degradation)
        if self.trace_enabled:
            try:
                trace = GuardTrace.from_decision(
                    decision={
                        "id": decision.model_dump().get("id", ""),
                        "decision": decision.decision,
                        "risk_score": decision.risk_score,
                        "evidence": decision.evidence,
                        "validation_results": [
                            r.model_dump() for r in decision.validator_results
                        ],
                    },
                    prompt=prompt,
                    output=output,
                    context=context,
                    domain=domain,
                )
                export_trace(trace)
            except Exception as e:
                logger.warning(
                    f"Failed to export trace: {e}. Validation result was not affected."
                )

        return decision

    async def validate_async(
        self,
        prompt: str,
        output: str,
        context: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> GuardDecision:
        """Validate model output asynchronously.

        Async wrapper around validate() using asyncio.to_thread. Allows
        non-blocking validation in async contexts without blocking the
        event loop.

        Args:
            prompt: User prompt or query that triggered the generation
            output: Model-generated text to validate
            context: Optional reference context
            domain: Optional domain metadata

        Returns:
            GuardDecision (same as validate())

        Raises:
            ValueError: If prompt or output are empty strings
            PolicyLoadError: Only if policy was invalid at initialization

        Example:
            >>> decision = await guard.validate_async(prompt, output, context)
            >>> if decision.decision == "allow":
            ...     return decision.output
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.validate,
            prompt,
            output,
            context,
            domain,
        )
