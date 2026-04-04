"""GuardedGemini — Gemini wrapper with automatic hallucination validation and ArmorIQ enforcement.

Wraps google.generativeai.GenerativeModel with:
  1. HallucinationGuard text validation (3-tier cascade)
  2. Optional ArmorIQ intent enforcement on tool/function calls

Usage (text validation only):
    >>> guarded = GuardedGemini(model=base_model, policy="rag_strict")
    >>> response = guarded.generate(prompt="What is AI?", context="AI stands for...")
    >>> print(response)

Usage (with ArmorIQ automatic enforcement):
    >>> from hallucination_guard.integrations.armoriq import ArmorIQAdapter, RuleBasedArmorIQClient
    >>> guarded = GuardedGemini(
    ...     model=base_model,
    ...     policy="rag_strict",
    ...     armoriq=ArmorIQAdapter(client=RuleBasedArmorIQClient()),
    ...     user_task="search for flights",
    ... )
    >>> # Tool calls in Gemini responses are automatically enforced against user_task
    >>> response = guarded.generate(prompt="Find me a flight to Paris.")
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional, Union

try:
    import google.generativeai as genai
    from google.generativeai.types import GenerateContentResponse  # noqa: F401
except ImportError:
    genai = None
    GenerateContentResponse = None

from hallucination_guard.core.guard import Guard
from hallucination_guard.core.exceptions import (
    HallucinationBlockedError,
    IntentViolationError,
    PolicyLoadError,
)
from hallucination_guard.policy.schema import PolicyConfig

logger = logging.getLogger(__name__)


class GuardedGemini:
    """Wrapper for google.generativeai.GenerativeModel with HallucinationGuard validation.

    Attributes:
        model: The underlying google.generativeai.GenerativeModel instance.
        guard: The initialized Guard instance for validation.
        policy: The loaded PolicyConfig governing validation behavior.
        max_retries: Maximum number of regeneration attempts on "regenerate" decision.
        armoriq: Optional ArmorIQAdapter for automatic action enforcement.
        user_task: Default task scope for ArmorIQ checks (can be overridden per-call).

    Example:
        >>> from hallucination_guard.integrations.armoriq import ArmorIQAdapter, RuleBasedArmorIQClient
        >>> guarded = GuardedGemini(
        ...     model=base_model,
        ...     policy="rag_strict",
        ...     max_retries=2,
        ...     armoriq=ArmorIQAdapter(client=RuleBasedArmorIQClient()),
        ...     user_task="search for flights to Paris",
        ... )
        >>> response = guarded.generate(prompt="Find me a flight to Paris.",
        ...                             context="Available flights are in the database.")
        >>> print(response)
    """

    def __init__(
        self,
        model: Optional[object] = None,
        policy: Union[str, Path, PolicyConfig] = "default",
        max_retries: int = 2,
        armoriq: Optional[Any] = None,
        user_task: Optional[str] = None,
    ) -> None:
        """Initialize GuardedGemini.

        Args:
            model: google.generativeai.GenerativeModel instance (auto-created if None).
            policy: Validation policy name, path, or PolicyConfig. Defaults to "default".
            max_retries: Max regeneration attempts on "regenerate" decision. Defaults to 2.
            armoriq: Optional ArmorIQAdapter. When set, Gemini function/tool calls are
                    automatically enforced for intent alignment after text validation.
                    Pass ArmorIQAdapter(client=RuleBasedArmorIQClient()) for offline mode.
                    Defaults to None (no enforcement).
            user_task: Default task scope for ArmorIQ. Overridable per-call. Falls back
                      to the prompt if neither is set. Defaults to None.

        Raises:
            ImportError: If google-generativeai is not installed.
            PolicyLoadError: If the policy cannot be loaded.
            ValueError: If model is None and cannot be auto-initialized.
        """
        if genai is None:
            raise ImportError(
                "google.generativeai is required for GuardedGemini. "
                "Install it with: pip install google-generativeai"
            )

        if model is not None:
            self.model = model
        else:
            try:
                self.model = genai.GenerativeModel("gemini-2.0-flash")
            except Exception as e:
                raise ValueError(
                    "Could not auto-initialize Gemini model. "
                    "Please pass model explicitly or ensure GOOGLE_API_KEY is set."
                ) from e

        try:
            self.guard = Guard(policy=policy)
            self.policy = self.guard.policy
        except PolicyLoadError as e:
            raise PolicyLoadError(policy_name=e.policy_name, reason=e.reason) from e

        self.max_retries = max(0, max_retries)
        self.armoriq = armoriq
        self.user_task = user_task

        armor_mode = "disabled"
        if armoriq is not None:
            armor_mode = "stub" if armoriq.client is None else "enforcement"

        logger.debug(
            f"GuardedGemini initialized: policy='{self.policy.name}', "
            f"max_retries={self.max_retries}, armoriq={armor_mode}"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        context: Optional[str] = None,
        domain: Optional[str] = None,
        user_task: Optional[str] = None,
    ) -> str:
        """Generate and validate a response from the underlying Gemini model.

        Calls generate_content(), validates the output through the 3-tier cascade,
        handles regeneration, and — if ArmorIQ is configured — automatically enforces
        any tool/function calls returned by Gemini.

        Decision handling:
            "allow"      → return text (+ ArmorIQ check if tool call present)
            "block"      → raise HallucinationBlockedError
            "regenerate" → retry with suggested_fix hint (up to max_retries)
            "abstain"    → log warning and return text

        Args:
            prompt: The user prompt to pass to Gemini.
            context: Optional reference context for faithfulness checking.
            domain: Optional domain tag (e.g. "healthcare") for policy tuning.
            user_task: Per-call ArmorIQ task scope override. Falls back to the
                      instance-level user_task, then to prompt.

        Returns:
            Validated response text from the model.

        Raises:
            HallucinationBlockedError: Validation failed and policy says block.
            IntentViolationError: ArmorIQ detected a misaligned tool call.
            ValueError: prompt is empty or not a string.
        """
        if not prompt or not isinstance(prompt, str):
            raise ValueError("prompt must be a non-empty string")

        attempt = 0
        current_prompt = prompt

        while attempt <= self.max_retries:
            try:
                model_response = self.model.generate_content(current_prompt)
                output = model_response.text

                decision = self.guard.validate(
                    prompt=prompt,
                    output=output,
                    context=context,
                    domain=domain,
                )

                if decision.prompt_security_metadata:
                    logger.info(
                        f"Prompt analysis: intent={decision.prompt_security_metadata.get('intent')}, "
                        f"injection_risk={decision.prompt_injection_risk:.2f}"
                    )

                if decision.decision == "allow":
                    logger.debug(
                        f"Output allowed (risk={decision.risk_score:.2f}, "
                        f"latency={decision.latency_ms:.1f}ms)"
                    )
                    self._enforce_action_if_needed(model_response, prompt, user_task)
                    return output

                elif decision.decision == "block":
                    logger.warning(
                        f"Output blocked (risk={decision.risk_score:.2f}): {decision.evidence}"
                    )
                    raise HallucinationBlockedError(
                        evidence=decision.evidence,
                        risk_score=decision.risk_score,
                        decision="block",
                    )

                elif decision.decision == "regenerate":
                    attempt += 1
                    if attempt > self.max_retries:
                        logger.warning(
                            f"Blocked after {self.max_retries} retries "
                            f"(risk={decision.risk_score:.2f}): {decision.evidence}"
                        )
                        raise HallucinationBlockedError(
                            evidence=decision.evidence,
                            risk_score=decision.risk_score,
                            decision="regenerate",
                        )
                    hint = decision.suggested_fix or (
                        "Please be more accurate and faithful to the provided context."
                    )
                    current_prompt = f"{prompt}\n\nHint: {hint}"
                    logger.info(f"Regenerating (attempt {attempt}/{self.max_retries}). Hint: {hint}")
                    continue

                elif decision.decision == "abstain":
                    logger.warning(
                        f"Validation inconclusive (confidence={decision.confidence:.2f}), "
                        f"returning response."
                    )
                    self._enforce_action_if_needed(model_response, prompt, user_task)
                    return output

                else:
                    logger.warning(f"Unexpected decision: {decision.decision}. Returning response.")
                    return output

            except (HallucinationBlockedError, IntentViolationError):
                raise
            except Exception as e:
                logger.error(f"Model generation failed: {e}")
                raise

        logger.error("Unexpected state: exited retry loop without returning or raising")
        raise RuntimeError("GuardedGemini internal error: retry loop exhausted")

    async def generate_async(
        self,
        prompt: str,
        context: Optional[str] = None,
        domain: Optional[str] = None,
        user_task: Optional[str] = None,
    ) -> str:
        """Async wrapper for generate() — runs in thread pool to avoid blocking.

        Args:
            prompt: User prompt to pass to Gemini.
            context: Optional reference context.
            domain: Optional domain metadata.
            user_task: Optional per-call ArmorIQ task scope.

        Returns:
            Validated response text.

        Raises:
            HallucinationBlockedError: Validation failed and policy says block.
            IntentViolationError: ArmorIQ detected a misaligned tool call.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.generate(prompt, context, domain, user_task),
        )

    def is_configured(self) -> bool:
        """Return True if GuardedGemini is properly initialized and ready to use."""
        try:
            return (
                genai is not None
                and self.model is not None
                and self.guard is not None
                and self.guard.policy is not None
            )
        except Exception as e:
            logger.warning(f"Configuration check failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_action_plan(self, model_response: Any) -> Optional[str]:
        """Extract a function/tool call from a Gemini response, if present.

        Inspects response candidates for function_call parts and formats
        them as a human-readable action_plan string for ArmorIQ enforcement.

        Args:
            model_response: Raw response from google.generativeai.

        Returns:
            Action string like "search_flights({'to': 'Paris'})", or None.
        """
        try:
            if not hasattr(model_response, "candidates"):
                return None
            for candidate in model_response.candidates:
                if not hasattr(candidate, "content"):
                    continue
                for part in candidate.content.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        fc = part.function_call
                        name = getattr(fc, "name", "unknown_tool")
                        args = dict(getattr(fc, "args", {}))
                        return f"{name}({args})"
        except Exception as e:
            logger.debug(f"Could not extract action plan from response: {e}")
        return None

    def _enforce_action_if_needed(
        self,
        model_response: Any,
        prompt: str,
        per_call_task: Optional[str],
    ) -> None:
        """Run ArmorIQ enforcement on tool calls if adapter is configured.

        Only executes when an ArmorIQAdapter is set AND the response contains a
        function/tool call. Raises IntentViolationError on misaligned actions.

        Task scope resolution order (highest → lowest priority):
            1. per_call_task (from this generate() call)
            2. self.user_task (instance-level default)
            3. prompt (fallback)

        Args:
            model_response: Raw Gemini response to inspect for tool calls.
            prompt: Original user prompt (task scope fallback).
            per_call_task: Per-call user_task override.

        Raises:
            IntentViolationError: If ArmorIQ detects a misaligned action.
        """
        if self.armoriq is None:
            return

        action_plan = self._extract_action_plan(model_response)
        if action_plan is None:
            return  # No tool call — nothing to enforce

        task = per_call_task or self.user_task or prompt
        logger.debug(f"ArmorIQ enforcing: task='{task}', action='{action_plan}'")
        self.armoriq.enforce(task, action_plan)
