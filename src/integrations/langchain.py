"""HallucinationGuardCallback - LangChain integration for RAG chain validation.

This module provides the HallucinationGuardCallback class, which integrates
HallucinationGuard validation into LangChain RAG chains. It operates as a
callback handler that captures context from retrievers and validates LLM
output before returning to the user.

It also optionally integrates ArmorIQ intent enforcement: when an
ArmorIQAdapter is passed, every tool call observed via on_tool_end is
enforced against the declared user_task before execution continues.

Typical usage (text validation only):
    >>> from langchain.chains import RetrievalQA
    >>> from verdict.integrations import HallucinationGuardCallback
    >>>
    >>> chain = RetrievalQA.from_chain_type(
    ...     llm=llm,
    ...     retriever=vector_store.as_retriever()
    ... )
    >>>
    >>> guard_callback = HallucinationGuardCallback(policy="rag_strict")
    >>> result = chain.run(
    ...     "What did the author say about AI safety?",
    ...     callbacks=[guard_callback]
    ... )
    >>> if result.metadata.get("guard_decision") == "block":
    ...     print(f"Blocked: {result.metadata['guard_evidence']}")

With ArmorIQ enforcement:
    >>> from verdict.integrations.armoriq import ArmorIQAdapter, RuleBasedArmorIQClient
    >>>
    >>> guard_callback = HallucinationGuardCallback(
    ...     policy="rag_strict",
    ...     armoriq=ArmorIQAdapter(client=RuleBasedArmorIQClient()),
    ...     user_task="search for flights to Paris",
    ... )
    >>> # Tool calls observed during chain execution are auto-enforced.

Design principles:
- Optional integration: langchain_core is an optional dependency
- Graceful degradation: callback failures never crash the LangChain pipeline
- Context capture: captured documents from retriever are joined as context
- Validation timing: validation occurs on llm_end, after generation completes
- ArmorIQ enforcement: tool calls enforced on tool_end, before execution result returned
- Immutable results: guard decisions are attached to metadata, never mutating output
"""

import logging
from typing import Any, Dict, List, Optional, Union
from pathlib import Path

try:
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.outputs import LLMResult
except ImportError:
    BaseCallbackHandler = None  # type: ignore
    LLMResult = None  # type: ignore

from verdict.core.guard import Guard
from verdict.core.decision import GuardDecision
from verdict.core.exceptions import (
    HallucinationBlockedError,
    IntentViolationError,
    PolicyLoadError,
)
from verdict.policy.schema import PolicyConfig

logger = logging.getLogger(__name__)


class HallucinationGuardCallback:
    """Callback handler for LangChain RAG chains with HallucinationGuard validation.

    HallucinationGuardCallback integrates HallucinationGuard validation into LangChain
    chains by capturing context from retrievers and validating LLM output. It also
    optionally integrates ArmorIQ intent enforcement for tool calls.

    The callback operates in three main phases:
    1. **Context capture** (on_retriever_end): Join retrieved documents as validation context
    2. **Tool enforcement** (on_tool_end): If ArmorIQ is configured, enforce tool call alignment
    3. **Output validation** (on_llm_end): Validate LLM output and attach decision to metadata

    If langchain_core is not installed, instantiation will raise ImportError with
    installation instructions.

    Attributes:
        guard: The initialized Guard instance for validation
        policy: The loaded PolicyConfig governing validation behavior
        armoriq: Optional ArmorIQAdapter for automatic tool call enforcement
        user_task: Declared task scope used for ArmorIQ enforcement

    Example (text validation only):
        >>> guard_callback = HallucinationGuardCallback(policy="rag_strict")
        >>> result = chain.run("What is AI?", callbacks=[guard_callback])
        >>> print(result.metadata["guard_decision"])

    Example (with ArmorIQ):
        >>> from verdict.integrations.armoriq import ArmorIQAdapter, RuleBasedArmorIQClient
        >>> guard_callback = HallucinationGuardCallback(
        ...     policy="rag_strict",
        ...     armoriq=ArmorIQAdapter(client=RuleBasedArmorIQClient()),
        ...     user_task="search for flights",
        ... )
        >>> # Tool calls are automatically enforced during chain execution
    """

    def __init__(
        self,
        policy: Union[str, Path, PolicyConfig] = "default",
        armoriq: Optional[Any] = None,
        user_task: Optional[str] = None,
    ) -> None:
        """Initialize HallucinationGuardCallback.

        Args:
            policy: Validation policy (name, path, or PolicyConfig object).
                   Defaults to "default".
            armoriq: Optional ArmorIQAdapter. When set, every tool call observed
                    via on_tool_end is enforced against user_task before the
                    LangChain chain receives the result. Raises IntentViolationError
                    on misaligned tool calls, halting the chain.
                    Pass ArmorIQAdapter(client=RuleBasedArmorIQClient()) for offline
                    enforcement. Defaults to None (no enforcement).
            user_task: Declared task scope for ArmorIQ enforcement. Falls back to
                      the captured prompt if not set. Defaults to None.

        Raises:
            ImportError: If langchain_core is not installed.
            PolicyLoadError: If policy cannot be loaded or validated.
        """
        if BaseCallbackHandler is None:
            raise ImportError(
                "langchain-core is required for HallucinationGuardCallback. "
                "Install it with: pip install langchain-core"
            )

        try:
            self.guard = Guard(policy=policy)
            self.policy = self.guard.policy
        except PolicyLoadError as e:
            raise PolicyLoadError(
                policy_name=e.policy_name,
                reason=e.reason,
            ) from e

        # Storage for captured retriever context and prompt (per callback instance)
        self._context: Optional[str] = None
        self._prompt: Optional[str] = None

        # ArmorIQ configuration
        self.armoriq = armoriq
        self.user_task = user_task

        armor_mode = "disabled"
        if armoriq is not None:
            armor_mode = "stub" if armoriq.client is None else "enforcement"

        logger.debug(
            f"HallucinationGuardCallback initialized: policy='{self.policy.name}', "
            f"armoriq={armor_mode}"
        )

    def on_retriever_end(
        self,
        documents: List[Any],
        *,
        run_id: str,
        parent_run_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Capture context from retriever documents.

        This callback is invoked when a retriever returns documents. The documents
        are joined with newlines to form a context string that will be used for
        validation.

        Args:
            documents: List of retrieved documents from the retriever
            run_id: Unique identifier for the retriever run
            parent_run_id: Optional parent run identifier
            **kwargs: Additional keyword arguments (ignored)

        Example:
            This is called automatically by LangChain when a retriever completes:
            >>> # User code (LangChain calls this automatically)
            >>> # callback.on_retriever_end(documents=[doc1, doc2, ...])
        """
        try:
            if not documents:
                logger.debug("No documents retrieved, context will be empty")
                self._context = ""
                return

            # Join documents into context string
            # Extract page_content if documents have it (Document objects),
            # otherwise use string representation
            context_parts = []
            for doc in documents:
                if hasattr(doc, "page_content"):
                    context_parts.append(doc.page_content)
                else:
                    context_parts.append(str(doc))

            self._context = "\n".join(context_parts)
            logger.debug(
                f"Captured {len(documents)} documents as context "
                f"({len(self._context)} chars)"
            )
        except Exception as e:
            logger.warning(f"Failed to capture retriever context: {e}")
            self._context = ""

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: str,
        parent_run_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Validate LLM output and attach decision to metadata.

        This callback is invoked when the LLM generates output. The output is
        validated against the captured context, and the validation decision is
        attached to response metadata for inspection by the caller.

        Validation decisions:
        - "allow": Output passes validation, returned as-is
        - "block": Output fails validation, marked in metadata
        - "regenerate": Output uncertain, marked in metadata
        - "abstain": Insufficient confidence, marked in metadata

        Args:
            response: LLMResult containing the generated output and metadata
            run_id: Unique identifier for the LLM run
            parent_run_id: Optional parent run identifier
            **kwargs: Additional keyword arguments (ignored)

        Raises:
            HallucinationBlockedError: If decision is "block" (optional, depends on policy)

        Note:
            - Validation failures are logged as warnings but never crash the callback
            - If validation raises an exception, a warning is logged and execution continues
            - The guard decision is always attached to metadata for inspection
        """
        try:
            # Extract output text from response
            if not response.generations or len(response.generations) == 0:
                logger.debug("No generations in LLM response, skipping validation")
                return

            # Get first generation (typically only one for single-shot generation)
            generation = response.generations[0]
            if not generation or len(generation) == 0:
                logger.debug("Empty generation, skipping validation")
                return

            output_text = generation[0].text

            # Validate output
            decision = self.guard.validate(
                prompt=self._prompt or "",
                output=output_text,
                context=self._context or "",
                domain="langchain_rag",  # Domain metadata for policy-based tuning
            )

            # Attach decision to metadata
            if not hasattr(response, "metadata") or response.metadata is None:
                response.metadata = {}

            response.metadata["guard_decision"] = decision.decision
            response.metadata["guard_risk_score"] = decision.risk_score
            response.metadata["guard_evidence"] = decision.evidence
            response.metadata["guard_latency_ms"] = decision.latency_ms
            response.metadata["guard_confidence"] = decision.confidence
            response.metadata["guard_prompt_injection_risk"] = decision.prompt_injection_risk
            response.metadata["guard_prompt_security_metadata"] = decision.prompt_security_metadata
            # Attach ArmorIQ enforcement metadata if available
            if decision.action_enforcement is not None:
                response.metadata["guard_action_enforcement"] = {
                    "enforced": decision.action_enforcement.enforced,
                    "allowed": decision.action_enforcement.allowed,
                    "user_task": decision.action_enforcement.user_task,
                    "action_plan": decision.action_enforcement.action_plan,
                    "reason": decision.action_enforcement.reason,
                }

            # Log decision
            logger.debug(
                f"Validation decision: {decision.decision} "
                f"(risk={decision.risk_score:.2f}, latency={decision.latency_ms:.1f}ms)"
            )

            # Handle block decision (raise exception if policy requires it)
            if decision.decision == "block":
                logger.warning(
                    f"Output blocked by validation (risk={decision.risk_score:.2f}): "
                    f"{decision.evidence}"
                )
                # Note: We do NOT raise here to allow LangChain to complete.
                # The caller should check metadata and handle the block decision.

        except HallucinationBlockedError as e:
            # Validation library error (should not happen in normal flow)
            logger.error(f"Validation blocked error: {e}")
            if hasattr(response, "metadata") and response.metadata is not None:
                response.metadata["guard_decision"] = "block"
                response.metadata["guard_evidence"] = str(e)
                response.metadata["guard_error"] = "validation_blocked"

        except Exception as e:
            # Any other error during validation
            logger.warning(f"Validation check failed: {e}")
            if hasattr(response, "metadata") and response.metadata is not None:
                response.metadata["guard_decision"] = "abstain"
                response.metadata["guard_evidence"] = f"Validation error: {e}"
                response.metadata["guard_error"] = str(type(e).__name__)

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: str,
        parent_run_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Capture the prompt at LLM start.

        This callback is invoked when the LLM is about to generate. The prompt
        is captured for use during validation.

        Args:
            serialized: Serialized LLM configuration
            prompts: List of prompts being sent to the LLM
            run_id: Unique identifier for the LLM run
            parent_run_id: Optional parent run identifier
            **kwargs: Additional keyword arguments (ignored)
        """
        try:
            if prompts and len(prompts) > 0:
                self._prompt = prompts[0]
                logger.debug(f"Captured prompt ({len(self._prompt)} chars)")
        except Exception as e:
            logger.warning(f"Failed to capture prompt: {e}")
            self._prompt = None

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: str,
        parent_run_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """Enforce ArmorIQ intent alignment on tool output/calls.

        This callback is invoked when a LangChain tool finishes executing.
        If an ArmorIQAdapter is configured, the tool name + output are checked
        against the declared user_task. A misaligned tool call raises
        IntentViolationError, halting the chain before the result is used.

        Graceful degradation: if ArmorIQ enforcement itself throws an unexpected
        error (other than IntentViolationError), it is logged and the chain
        continues normally.

        Args:
            output: The output/result string from the tool.
            run_id: Unique identifier for the tool run.
            parent_run_id: Optional parent run identifier.
            **kwargs: May include 'name' (tool name) passed by some LangChain versions.

        Raises:
            IntentViolationError: If ArmorIQ is configured and detects a
                                 misaligned tool call.
        """
        if self.armoriq is None:
            return

        try:
            # Resolve tool name if provided by LangChain
            tool_name = kwargs.get("name", "unknown_tool")
            action_plan = f"{tool_name}: {output}" if tool_name != "unknown_tool" else output
            task = self.user_task or self._prompt or "unknown task"

            logger.debug(
                f"ArmorIQ tool enforcement: task='{task}', "
                f"action='{action_plan[:80]}...'"
            )
            self.armoriq.enforce(task, action_plan)
            logger.debug("ArmorIQ: tool call allowed")

        except IntentViolationError:
            # Re-raise to halt the LangChain chain
            raise
        except Exception as e:
            # Any other error: log and continue (graceful degradation)
            logger.warning(f"ArmorIQ tool enforcement failed unexpectedly: {e}. Allowing action.")

    def is_configured(self) -> bool:
        """Check if HallucinationGuardCallback is properly configured and ready.

        Returns:
            True if callback is ready to validate, False otherwise

        Example:
            >>> callback = HallucinationGuardCallback(policy="rag_strict")
            >>> if callback.is_configured():
            ...     print("Callback is ready")
        """
        try:
            return (
                self.guard is not None
                and self.guard.policy is not None
                and self.policy is not None
            )
        except Exception as e:
            logger.warning(f"Configuration check failed: {e}")
            return False
