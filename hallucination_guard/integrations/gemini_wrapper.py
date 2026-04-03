"""GuardedGemini - Wrapper for Google Generative AI (Gemini) with HallucinationGuard validation.

This module provides the GuardedGemini class, which wraps google.generativeai.GenerativeModel
with automatic hallucination validation and regeneration logic. It is the primary integration
for the HallucinationGuard SDK hackathon demo.

Typical usage:
    >>> from hallucination_guard.integrations import GuardedGemini
    >>> import google.generativeai as genai
    >>>
    >>> genai.configure(api_key="...")
    >>> base_model = genai.GenerativeModel("gemini-2.0-flash")
    >>>
    >>> guarded = GuardedGemini(
    ...     model=base_model,
    ...     policy="rag_strict",
    ...     max_retries=2
    ... )
    >>>
    >>> response = guarded.generate(
    ...     prompt="What is AI?",
    ...     context="AI is artificial intelligence..."
    ... )
    >>> print(response.text)  # Only returned if validation passes

Design principles:
- Zero mandatory API calls—validation happens locally with cached models
- Graceful degradation—if Gemini API fails, raise appropriately; validation failures
  are handled per policy (allow/block/regenerate/abstain)
- Auto-regeneration—when decision is "regenerate", automatically retry with a hint
  for up to max_retries attempts
- Immutable results—GuardedGemini always returns or raises, never mutates input
"""

import asyncio
import logging
from typing import Optional, Union
from pathlib import Path

try:
    import google.generativeai as genai
    from google.generativeai.types import GenerateContentResponse
except ImportError:
    genai = None
    GenerateContentResponse = None

from hallucination_guard.core.guard import Guard
from hallucination_guard.core.decision import GuardDecision
from hallucination_guard.core.exceptions import HallucinationBlockedError, PolicyLoadError
from hallucination_guard.policy.schema import PolicyConfig

logger = logging.getLogger(__name__)


class GuardedGemini:
    """Wrapper for google.generativeai.GenerativeModel with HallucinationGuard validation.

    GuardedGemini automatically validates Gemini model outputs using HallucinationGuard
    and implements regeneration logic with configurable retry limits. It is designed
    for RAG applications and other scenarios where hallucination prevention is critical.

    Attributes:
        model: The underlying google.generativeai.GenerativeModel instance
        guard: The initialized Guard instance for validation
        policy: The loaded PolicyConfig governing validation behavior
        max_retries: Maximum number of regeneration attempts on "regenerate" decision

    Example:
        >>> guarded = GuardedGemini(
        ...     model=base_model,
        ...     policy="rag_strict",
        ...     max_retries=2
        ... )
        >>> response = guarded.generate(
        ...     prompt="Summarize this paper.",
        ...     context=paper_text
        ... )
        >>> print(response.text)
    """

    def __init__(
        self,
        model: Optional[object] = None,
        policy: Union[str, Path, PolicyConfig] = "default",
        max_retries: int = 2,
    ) -> None:
        """Initialize GuardedGemini with a base model and validation policy.

        Args:
            model: google.generativeai.GenerativeModel instance. If not provided,
                   will attempt to create one using genai.GenerativeModel("gemini-2.0-flash").
            policy: Validation policy (name, path, or PolicyConfig object).
                   Defaults to "default".
            max_retries: Maximum number of regeneration attempts when decision is
                        "regenerate". Defaults to 2.

        Raises:
            ImportError: If google.generativeai is not installed
            PolicyLoadError: If policy cannot be loaded or validated
            ValueError: If model is None and cannot be auto-initialized

        Example:
            >>> guarded = GuardedGemini(
            ...     model=my_gemini_model,
            ...     policy="rag_strict",
            ...     max_retries=2
            ... )
        """
        # Verify google.generativeai is available
        if genai is None:
            raise ImportError(
                "google.generativeai is required for GuardedGemini. "
                "Install it with: pip install google-generativeai"
            )

        # Store or initialize model
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

        # Initialize Guard with policy
        try:
            self.guard = Guard(policy=policy)
            self.policy = self.guard.policy
        except PolicyLoadError as e:
            raise PolicyLoadError(
                policy_name=e.policy_name,
                reason=e.reason,
            ) from e

        # Store retry limit
        self.max_retries = max(0, max_retries)

        logger.debug(
            f"GuardedGemini initialized with policy '{self.policy.name}' "
            f"(max_retries={self.max_retries})"
        )

    def generate(
        self,
        prompt: str,
        context: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> str:
        """Generate and validate output from the underlying Gemini model.

        This is the primary method for GuardedGemini. It calls the base model's
        generate_content() method, validates the output, and handles regeneration
        logic based on the validation decision:

        - "allow": Return the response text immediately
        - "block": Raise HallucinationBlockedError with evidence
        - "regenerate": Retry generation with a suggested_fix hint (up to max_retries)
        - "abstain": Log a warning and return the response text (insufficient confidence)

        Args:
            prompt: User prompt or query to pass to Gemini
            context: Optional reference context (e.g., from RAG retriever).
                    Used by validators to check faithfulness.
            domain: Optional domain metadata (e.g., "healthcare", "finance").
                   Used for policy-based tuning.

        Returns:
            The validated response text from the model.

        Raises:
            HallucinationBlockedError: If validation fails and policy action is "block"
            ValueError: If prompt is empty
            Exception: Model API errors (network, quota, etc.) are re-raised

        Example:
            >>> try:
            ...     response = guarded.generate(
            ...         prompt="What is AI?",
            ...         context="AI stands for artificial intelligence..."
            ...     )
            ...     print(response)
            ... except HallucinationBlockedError as e:
            ...     print(f"Blocked (risk={e.risk_score:.2f}): {e.evidence}")
        """
        if not prompt or not isinstance(prompt, str):
            raise ValueError("prompt must be a non-empty string")

        attempt = 0
        current_prompt = prompt

        while attempt <= self.max_retries:
            try:
                # Generate content from base model
                model_response = self.model.generate_content(current_prompt)
                output = model_response.text

                # Validate output
                decision = self.guard.validate(
                    prompt=prompt,  # Always use original prompt for validation
                    output=output,
                    context=context,
                    domain=domain,
                )

                # Log prompt security metadata if available
                if decision.prompt_security_metadata:
                    logger.info(
                        f"Prompt analysis: intent={decision.prompt_security_metadata.get('intent')}, "
                        f"sensitivity_tags={decision.prompt_security_metadata.get('sensitivity_tags')}, "
                        f"injection_risk={decision.prompt_injection_risk:.2f}"
                    )

                # Handle decision
                if decision.decision == "allow":
                    logger.debug(
                        f"Output allowed (risk={decision.risk_score:.2f}, "
                        f"latency={decision.latency_ms:.1f}ms)"
                    )
                    return output

                elif decision.decision == "block":
                    logger.warning(
                        f"Output blocked (risk={decision.risk_score:.2f}, "
                        f"latency={decision.latency_ms:.1f}ms): {decision.evidence}"
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
                            f"Output blocked after {self.max_retries} regeneration "
                            f"attempts (risk={decision.risk_score:.2f}): "
                            f"{decision.evidence}"
                        )
                        raise HallucinationBlockedError(
                            evidence=decision.evidence,
                            risk_score=decision.risk_score,
                            decision="regenerate",
                        )

                    # Prepare retry prompt with suggested fix
                    hint = decision.suggested_fix or "Please be more accurate and faithful to the provided context."
                    current_prompt = f"{prompt}\n\nHint: {hint}"
                    logger.info(
                        f"Regenerating (attempt {attempt}/{self.max_retries}). "
                        f"Hint: {hint}"
                    )
                    continue

                elif decision.decision == "abstain":
                    logger.warning(
                        f"Output validation inconclusive (confidence={decision.confidence:.2f}), "
                        f"returning response: {decision.evidence}"
                    )
                    return output

                else:
                    # Fallback for unexpected decision types
                    logger.warning(
                        f"Unexpected decision type: {decision.decision}. "
                        f"Returning response."
                    )
                    return output

            except HallucinationBlockedError:
                # Re-raise validation blocks (don't retry)
                raise
            except Exception as e:
                # Model API errors (network, quota, etc.)
                logger.error(f"Model generation failed: {e}")
                raise

        # Should not reach here, but safety fallback
        logger.error("Unexpected state: exited retry loop without returning or raising")
        raise RuntimeError("GuardedGemini internal error: retry loop exhausted")

    async def generate_async(
        self,
        prompt: str,
        context: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> str:
        """Async wrapper for generate() using asyncio.

        This method allows non-blocking generation in async contexts. It runs the
        synchronous generate() method in a thread pool to avoid blocking the event loop.

        Args:
            prompt: User prompt or query to pass to Gemini
            context: Optional reference context
            domain: Optional domain metadata

        Returns:
            The validated response text from the model.

        Raises:
            HallucinationBlockedError: If validation fails and policy action is "block"
            ValueError: If prompt is empty
            Exception: Model API errors are re-raised

        Example:
            >>> async def main():
            ...     response = await guarded.generate_async(
            ...         prompt="What is AI?",
            ...         context="AI stands for artificial intelligence..."
            ...     )
            ...     print(response)
            >>>
            >>> asyncio.run(main())
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.generate,
            prompt,
            context,
            domain,
        )

    def is_configured(self) -> bool:
        """Check if GuardedGemini is properly configured and ready to use.

        This method verifies that:
        - google.generativeai is installed
        - The base model is initialized
        - The Guard policy is loaded

        Returns:
            True if GuardedGemini is ready to generate, False otherwise

        Example:
            >>> if guarded.is_configured():
            ...     response = guarded.generate(prompt)
            ... else:
            ...     print("GuardedGemini not properly configured")
        """
        try:
            if genai is None:
                return False
            if self.model is None:
                return False
            if self.guard is None or self.guard.policy is None:
                return False
            return True
        except Exception as e:
            logger.warning(f"Configuration check failed: {e}")
            return False
