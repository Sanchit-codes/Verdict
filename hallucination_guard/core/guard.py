"""Main Guard class - public API entry point for HallucinationGuard validation.

This module provides the primary user-facing Guard class that wraps the
validation pipeline, decision engine, and trace export system. Guard is
designed to be simple to use while supporting advanced customization.

Typical usage (text validation only):
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

With ArmorIQ intent enforcement:
    >>> from hallucination_guard.integrations.armoriq import ArmorIQAdapter, RuleBasedArmorIQClient
    >>>
    >>> guard = Guard(
    ...     policy="rag_strict",
    ...     armoriq=ArmorIQAdapter(client=RuleBasedArmorIQClient()),
    ... )
    >>> decision = guard.validate(
    ...     prompt="What flights are available?",
    ...     output="Available flights are ...",
    ...     context="Database of flights...",
    ...     action_plan="search_flights({'to': 'Paris'})",
    ...     user_task="search for flights",
    ... )
    >>> print(decision.action_enforcement)  # ActionEnforcementResult
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Optional, Union

from hallucination_guard.core.decision import ActionEnforcementResult, GuardDecision
from hallucination_guard.core.exceptions import IntentViolationError, PolicyLoadError
from hallucination_guard.core.pipeline import ValidationPipeline
from hallucination_guard.core.trace import GuardTrace, export_trace
from hallucination_guard.policy.loader import load_policy as _load_policy
from hallucination_guard.policy.schema import PolicyConfig
from hallucination_guard.validators.base import ValidationInput
from hallucination_guard.validators.embedding import preload_embedding
from hallucination_guard.validators.hhem import preload_hhem

logger = logging.getLogger(__name__)


class Guard:
    """Main validation API for HallucinationGuard.

    Guard is the entry point for both text validation and optional ArmorIQ
    intent enforcement. It wraps the validation pipeline, decision engine,
    and optional trace export system.

    Attributes:
        policy: The loaded PolicyConfig governing validation behavior.
        pipeline: The ValidationPipeline orchestrator.
        trace_enabled: Whether to export traces after each validation.
        armoriq: Optional ArmorIQAdapter for action enforcement.

    Example (text only):
        >>> guard = Guard(policy="default")
        >>> decision = guard.validate(prompt, output, context)
        >>> if decision.decision == "allow":
        ...     return decision.output

    Example (with ArmorIQ):
        >>> from hallucination_guard.integrations.armoriq import ArmorIQAdapter, RuleBasedArmorIQClient
        >>> guard = Guard(
        ...     policy="rag_strict",
        ...     armoriq=ArmorIQAdapter(client=RuleBasedArmorIQClient()),
        ... )
        >>> decision = guard.validate(
        ...     prompt="Search for flights",
        ...     output="Found 3 flights to Paris",
        ...     context="Available flights: ...",
        ...     action_plan="search_flights({'to': 'Paris'})",
        ...     user_task="search for flights",
        ... )
        >>> print(decision.action_enforcement.allowed)  # True
    """

    def __init__(
        self,
        policy: Union[str, Path, PolicyConfig],
        trace_enabled: Optional[bool] = None,
        enable_prompt_validators: bool = True,
        armoriq: Optional[Any] = None,
        preload_models: bool = False,
    ) -> None:
        """Initialize Guard with a policy configuration.

        Args:
            policy: Policy name ("default", "rag_strict", "chatbot"),
                   file path, or PolicyConfig object.
            trace_enabled: Whether to export traces. Auto-enables if
                          LANGFUSE_PUBLIC_KEY is set and this is None.
            enable_prompt_validators: Whether to enable Tier 0.5 prompt security.
                                     Defaults to True.
            armoriq: Optional ArmorIQAdapter for action enforcement. When set,
                    validate() checks action_plan alignment after text passes.
                    Pass ArmorIQAdapter(client=RuleBasedArmorIQClient()) for
                    offline enforcement. Defaults to None (no enforcement).
            preload_models: Whether to preload embedding and HHEM models during initialization
                          to eliminate first-run latency spikes. Default False for backward
                          compatibility. Can also be enabled via HG_PRELOAD_MODELS=true
                          environment variable. Preload failures are logged but don't crash.

        Raises:
            PolicyLoadError: If policy cannot be loaded or validated.
            ValueError: If policy argument type is invalid.
            >>>
            >>> # With model preloading enabled
            >>> guard5 = Guard(policy="default", preload_models=True)
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

        # Store prompt validator setting
        self.enable_prompt_validators = enable_prompt_validators

        # Initialize pipeline with loaded policy
        self.pipeline = ValidationPipeline(self.policy)

        # Store optional ArmorIQ adapter
        self.armoriq = armoriq

        # Determine trace settings
        if trace_enabled is None:
            langfuse_key = os.getenv("LANGFUSE_PUBLIC_KEY")
            self.trace_enabled = langfuse_key is not None
        else:
            self.trace_enabled = trace_enabled

        armor_mode = "disabled"
        if armoriq is not None:
            armor_mode = "stub" if armoriq.client is None else "enforcement"

        # Preload models if requested
        should_preload = preload_models or os.getenv("HG_PRELOAD_MODELS", "").lower() == "true"
        if should_preload:
            logger.info("Preloading validation models...")
            try:
                embedding_ok = preload_embedding()
                hhem_ok = preload_hhem()
                if embedding_ok and hhem_ok:
                    logger.info("Models preloaded successfully")
                elif embedding_ok:
                    logger.warning("Embedding preloaded, HHEM unavailable")
                elif hhem_ok:
                    logger.warning("HHEM preloaded, embedding unavailable")
                else:
                    logger.warning("Model preload failed, will use lazy loading")
            except Exception as e:
                logger.warning(f"Model preload failed: {e}, will use lazy loading")

        logger.debug(
            f"Guard initialized with policy '{self.policy.name}' "
            f"(trace_enabled={self.trace_enabled}, "
            f"enable_prompt_validators={self.enable_prompt_validators}, "
            f"armoriq={armor_mode})"
        )

    def validate(
        self,
        prompt: str,
        output: str,
        context: Optional[str] = None,
        domain: Optional[str] = None,
        action_plan: Optional[str] = None,
        user_task: Optional[str] = None,
    ) -> GuardDecision:
        """Validate model output synchronously, with optional ArmorIQ enforcement.

        Runs the four-tier validation pipeline (Tier 0.5 + Tiers 1-3). If
        ArmorIQ is configured and an action_plan is provided, intent enforcement
        runs after text validation passes and the result is stored in
        decision.action_enforcement.

        Does NOT auto-raise exceptions — callers check decision.decision and
        raise exceptions manually if desired. IntentViolationError is the
        exception to this rule: it IS raised when ArmorIQ blocks an action.

        Args:
            prompt: User prompt or query that triggered the generation.
            output: Model-generated text to validate.
            context: Optional reference context (e.g., retrieved documents).
            domain: Optional domain metadata (e.g., "healthcare", "finance").
            action_plan: Optional action to enforce with ArmorIQ (e.g., a tool
                        call string). If None, ArmorIQ enforcement is skipped.
            user_task: Declared task scope for ArmorIQ. Falls back to prompt.
                      Only used when action_plan is provided.

        Returns:
            GuardDecision with decision, risk_score, evidence, validator_results,
            latency_ms, and action_enforcement (ActionEnforcementResult or None).

        Raises:
            ValueError: If prompt or output are empty strings.
            IntentViolationError: If ArmorIQ is configured and action is misaligned.
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

        # Run text validation pipeline
        decision = self.pipeline.run(validation_input)

        # --- ArmorIQ: enforce action intent AFTER text validation ---
        enforcement_result: Optional[ActionEnforcementResult] = None
        if self.armoriq is not None and action_plan is not None:
            task = user_task or prompt
            try:
                self.armoriq.enforce(task, action_plan)
                enforcement_result = ActionEnforcementResult(
                    enforced=True,
                    allowed=True,
                    user_task=task,
                    action_plan=action_plan,
                    reason=None,
                )
                logger.debug(f"ArmorIQ: action allowed (task='{task}'")
            except IntentViolationError as e:
                enforcement_result = ActionEnforcementResult(
                    enforced=True,
                    allowed=False,
                    user_task=task,
                    action_plan=action_plan,
                    reason=e.reason,
                )
                logger.warning(f"ArmorIQ: action blocked — {e.reason}")
                # Re-raise so callers can handle the violation
                raise

        # Attach enforcement result to decision (immutable update)
        if enforcement_result is not None:
            decision = decision.model_copy(update={"action_enforcement": enforcement_result})

        # Export trace if enabled (with graceful degradation)
        if self.trace_enabled:
            try:
                trace = GuardTrace.from_decision(
                    decision={
                        "decision": decision.decision,
                        "risk_score": decision.risk_score,
                        "evidence": decision.evidence,
                        "validation_results": [
                            r.model_dump() for r in decision.validator_results
                        ],
                        "policy_name": decision.policy_name,
                        "latency_ms": decision.latency_ms,
                        "confidence": decision.confidence,
                        "prompt_injection_risk": decision.prompt_injection_risk,
                        "prompt_security_metadata": decision.prompt_security_metadata,
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
        action_plan: Optional[str] = None,
        user_task: Optional[str] = None,
    ) -> GuardDecision:
        """Validate model output asynchronously.

        Async wrapper around validate() using asyncio.run_in_executor.
        Allows non-blocking validation in async contexts.

        Args:
            prompt: User prompt or query that triggered the generation.
            output: Model-generated text to validate.
            context: Optional reference context.
            domain: Optional domain metadata.
            action_plan: Optional action for ArmorIQ enforcement.
            user_task: Declared task scope for ArmorIQ enforcement.

        Returns:
            GuardDecision (same as validate()).

        Raises:
            ValueError: If prompt or output are empty strings.
            IntentViolationError: If ArmorIQ detects a misaligned action.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.validate(prompt, output, context, domain, action_plan, user_task),
        )
