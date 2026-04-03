"""GuardedLocalModel - Wrapper for local LLM instances with HallucinationGuard validation.

This module provides the GuardedLocalModel class, which wraps local model instances
(e.g., from llama-cpp-python, ollama, or other local inference engines) with automatic
hallucination validation and regeneration logic.

Typical usage:
    >>> from hallucination_guard.integrations import GuardedLocalModel
    >>> from llama_cpp import Llama
    >>>
    >>> # Load a local model (example: llama-cpp-python)
    >>> local_model = Llama(model_path="./models/llama-2-7b.gguf")
    >>>
    >>> guarded = GuardedLocalModel(
    ...     model=local_model,
    ...     policy="rag_strict",
    ...     max_retries=2
    ... )
    >>>
    >>> response = guarded.generate(
    ...     prompt="What is AI?",
    ...     context="AI is artificial intelligence..."
    ... )
    >>> print(response)  # Only returned if validation passes

Design principles:
- Generic model interface—accepts any model instance with a generate() or similar method
- Zero mandatory API calls—validation happens locally with cached models
- Graceful degradation—if local model fails, raise appropriately; validation failures
  are handled per policy (allow/block/regenerate/abstain)
- Auto-regeneration—when decision is "regenerate", automatically retry with a hint
  for up to max_retries attempts
- Immutable results—GuardedLocalModel always returns or raises, never mutates input
"""

import asyncio
import logging
from typing import Any, Callable, Optional, Union
from pathlib import Path

from hallucination_guard.core.guard import Guard
from hallucination_guard.core.decision import GuardDecision
from hallucination_guard.core.exceptions import HallucinationBlockedError, PolicyLoadError
from hallucination_guard.policy.schema import PolicyConfig

logger = logging.getLogger(__name__)


class GuardedLocalModel:
    """Wrapper for local LLM instances with HallucinationGuard validation.

    GuardedLocalModel automatically validates local model outputs using HallucinationGuard
    and implements regeneration logic with configurable retry limits. It is designed
    for scenarios where you want to run inference locally (e.g., llama-cpp-python, ollama)
    while ensuring output quality through hallucination detection.

    The model is expected to have a method that generates text from a prompt. This method
    is specified via the `generate_fn` parameter or determined by introspection.

    Attributes:
        model: The underlying local model instance
        guard: The initialized Guard instance for validation
        policy: The loaded PolicyConfig governing validation behavior
        max_retries: Maximum number of regeneration attempts on "regenerate" decision
        generate_fn: The callable method on the model that generates text

    Example:
        >>> from llama_cpp import Llama
        >>> local_model = Llama(model_path="./models/llama-2-7b.gguf")
        >>> guarded = GuardedLocalModel(
        ...     model=local_model,
        ...     policy="rag_strict",
        ...     max_retries=2
        ... )
        >>> response = guarded.generate(
        ...     prompt="Summarize this paper.",
        ...     context=paper_text
        ... )
        >>> print(response)
    """

    def __init__(
        self,
        model: object,
        policy: Union[str, Path, PolicyConfig] = "default",
        max_retries: int = 2,
        generate_fn: Optional[Callable[[str], str]] = None,
    ) -> None:
        """Initialize GuardedLocalModel with a base model and validation policy.

        Args:
            model: Local model instance. Must have a method to generate text from a prompt.
            policy: Validation policy (name, path, or PolicyConfig object).
                   Defaults to "default".
            max_retries: Maximum number of regeneration attempts when decision is
                        "regenerate". Defaults to 2.
            generate_fn: Optional callable that takes a prompt string and returns generated text.
                        If not provided, will look for common method names like generate(),
                        __call__(), generate_content(), or completion().

        Raises:
            PolicyLoadError: If policy cannot be loaded or validated
            ValueError: If model is None or no generate function can be found
            TypeError: If generate_fn is provided but not callable

        Example:
            >>> from llama_cpp import Llama
            >>> local_model = Llama(model_path="./models/llama-2-7b.gguf")
            >>> guarded = GuardedLocalModel(
            ...     model=local_model,
            ...     policy="rag_strict",
            ...     max_retries=2
            ... )
        """
        # Validate model is not None
        if model is None:
            raise ValueError("model cannot be None. Please provide a valid model instance.")

        self.model = model

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

        # Determine generate function
        if generate_fn is not None:
            if not callable(generate_fn):
                raise TypeError("generate_fn must be callable")
            self.generate_fn = generate_fn
        else:
            # Try common method names
            for method_name in ["generate", "__call__", "generate_content", "completion"]:
                if hasattr(self.model, method_name):
                    self.generate_fn = getattr(self.model, method_name)
                    logger.debug(f"Auto-detected generate method: {method_name}")
                    break
            else:
                raise ValueError(
                    "Could not find a generate method on the model. "
                    "Please pass generate_fn explicitly with a callable that takes a prompt "
                    "and returns generated text."
                )

        logger.debug(
            f"GuardedLocalModel initialized with policy '{self.policy.name}' "
            f"(max_retries={self.max_retries})"
        )

    def generate(
        self,
        prompt: str,
        context: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> str:
        """Generate and validate output from the underlying local model.

        This is the primary method for GuardedLocalModel. It calls the base model's
        generate function, validates the output, and handles regeneration logic based
        on the validation decision:

        - "allow": Return the response text immediately
        - "block": Raise HallucinationBlockedError with evidence
        - "regenerate": Retry generation with a suggested_fix hint (up to max_retries)
        - "abstain": Log a warning and return the response text (insufficient confidence)

        Args:
            prompt: User prompt or query to pass to the local model
            context: Optional reference context (e.g., from RAG retriever).
                    Used by validators to check faithfulness.
            domain: Optional domain metadata (e.g., "healthcare", "finance").
                   Used for policy-based tuning.

        Returns:
            The validated response text from the model.

        Raises:
            HallucinationBlockedError: If validation fails and policy action is "block"
            ValueError: If prompt is empty
            Exception: Model generation errors are re-raised with context

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
                output = self.generate_fn(current_prompt)

                # Handle non-string outputs gracefully
                if not isinstance(output, str):
                    logger.warning(
                        f"Model returned non-string output (type={type(output).__name__}), "
                        f"converting to string"
                    )
                    output = str(output)

                # Validate output
                decision = self.guard.validate(
                    prompt=prompt,  # Always use original prompt for validation
                    output=output,
                    context=context,
                    domain=domain,
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
                # Model generation errors
                logger.error(f"Model generation failed: {e}")
                raise

        # Should not reach here, but safety fallback
        logger.error("Unexpected state: exited retry loop without returning or raising")
        raise RuntimeError("GuardedLocalModel internal error: retry loop exhausted")

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
            prompt: User prompt or query to pass to the local model
            context: Optional reference context
            domain: Optional domain metadata

        Returns:
            The validated response text from the model.

        Raises:
            HallucinationBlockedError: If validation fails and policy action is "block"
            ValueError: If prompt is empty
            Exception: Model generation errors are re-raised

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
        """Check if GuardedLocalModel is properly configured and ready to use.

        This method verifies that:
        - The base model is initialized
        - The generate function is available
        - The Guard policy is loaded

        Returns:
            True if GuardedLocalModel is ready to generate, False otherwise

        Example:
            >>> if guarded.is_configured():
            ...     response = guarded.generate(prompt)
            ... else:
            ...     print("GuardedLocalModel not properly configured")
        """
        try:
            if self.model is None:
                return False
            if not callable(self.generate_fn):
                return False
            if self.guard is None or self.guard.policy is None:
                return False
            return True
        except Exception as e:
            logger.warning(f"Configuration check failed: {e}")
            return False
