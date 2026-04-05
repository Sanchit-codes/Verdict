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
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from hallucination_guard.core.decision import ActionEnforcementResult, GuardDecision
from hallucination_guard.core.exceptions import IntentViolationError, PolicyLoadError
from hallucination_guard.core.pipeline import ValidationPipeline
from hallucination_guard.core.trace import GuardTrace, export_trace
from hallucination_guard.policy.loader import load_policy as _load_policy
from hallucination_guard.policy.schema import PolicyConfig
from hallucination_guard.validators.base import ValidationInput
from hallucination_guard.validators.embedding import preload_embedding
from hallucination_guard.validators.hhem import preload_hhem
from hallucination_guard.preprocessing.ground_truth import GroundTruthContext

# Preprocessing imports (lazy — only loaded when preprocessing is enabled)
try:
    from hallucination_guard.preprocessing.prompt_analyzer import PromptAnalyzer
    from hallucination_guard.preprocessing.context_manager import ContextManager
    from hallucination_guard.preprocessing.prompt_compactor import PromptCompactor
    _PREPROCESSING_AVAILABLE = True
except ImportError:
    _PREPROCESSING_AVAILABLE = False

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
    # Class-level in-memory storage for ground truth contexts (session-keyed)
    _ground_truth_store: Dict[str, GroundTruthContext] = {}

    def __init__(
        self,
        policy: Union[str, Path, PolicyConfig],
        trace_enabled: Optional[bool] = None,
        enable_prompt_validators: bool = True,
        armoriq: Optional[Any] = None,
        preload_models: bool = False,
        preprocessing: bool = False,
        fast_mode: bool = False,
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
            preprocessing: Enable the preprocessing layer for use with
                          ``generate_and_validate()``. Initialises PromptAnalyzer,
                          ContextManager, and PromptCompactor. Has no effect on the
                          existing ``validate()`` method. Defaults to False.
            fast_mode: When True, prefer low-latency validation by disabling heavy
                       Tier 2 (embedding) and Tier 3 (HHEM) validators at runtime,
                       even if enabled in the policy. Defaults to False.

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

        # Fast mode: disable heavy validators (embedding + HHEM) at runtime,
        # regardless of what the policy enables. This is a coarse, per-Guard
        # toggle intended for environments where model loading is too slow.
        self.fast_mode = fast_mode

        # Build an effective policy view for this Guard instance. PolicyConfig
        # and ValidatorConfig are frozen, so we must not mutate them in place.
        # Instead we create a shallow copy with validators adjusted according to
        # fast_mode. Other Guard instances using the same PolicyConfig remain
        # unaffected.
        if self.fast_mode:
            disabled = {"embedding", "hhem"}
            validators = [
                v for v in self.policy.validators if v.name not in disabled
            ]
            self._effective_policy = self.policy.model_copy(update={"validators": validators})
        else:
            self._effective_policy = self.policy

        # Initialize pipeline with the effective policy for this Guard.
        # Heavy validator behavior can be further controlled via runtime
        # flags (e.g. fast_mode) without mutating the original PolicyConfig.
        self.pipeline = ValidationPipeline(self._effective_policy)


        # Store optional ArmorIQ adapter
        self.armoriq = armoriq

        # Preprocessing layer (opt-in)
        self.preprocessing_enabled = preprocessing and _PREPROCESSING_AVAILABLE
        if preprocessing and not _PREPROCESSING_AVAILABLE:
            logger.warning(
                "Guard: preprocessing=True but preprocessing module not importable. "
                "Continuing without preprocessing."
            )
        if self.preprocessing_enabled:
            self._analyzer = PromptAnalyzer()  # type: ignore[name-defined]
            self._context_mgr = ContextManager()  # type: ignore[name-defined]
            self._compactor = PromptCompactor()  # type: ignore[name-defined]
            logger.debug("Guard: preprocessing layer initialised")

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

    # ------------------------------------------------------------------
    # Full pipeline: Preprocess → Generate → ArmorIQ → Validate
    # ------------------------------------------------------------------

    def _store_ground_truth(self, session_key: str, ground_truth: GroundTruthContext) -> None:
        """Store ground truth context for a session."""
        self.__class__._ground_truth_store[session_key] = ground_truth

    def _get_ground_truth(self, session_key: str) -> Optional[GroundTruthContext]:
        """Retrieve ground truth context for a session."""
        return self.__class__._ground_truth_store.get(session_key)

    def _get_session_task(self, session_key: str) -> Optional[str]:
        """Get the task description from stored ground truth."""
        gt = self._get_ground_truth(session_key)
        return gt.task_description() if gt else None

    def _check_thinking_for_intent(
        self, thinking: str, task: str
    ) -> Optional[str]:
        """Check if LLM thinking reveals intent misalignment.
        
        Args:
            thinking: The LLM's reasoning/thinking process.
            task: The declared user task.
            
        Returns:
            None if aligned, or error message if misaligned.
        """
        if not self.armoriq or not thinking:
            return None
        
        try:
            self.armoriq.enforce(task, thinking)
            logger.debug(f"Thinking process aligned with task")
            return None
        except Exception as e:
            error_msg = f"Intent violation in thinking process: {str(e)}"
            logger.warning(error_msg)
            return error_msg

    def _extract_actions_from_response(self, response_text: str) -> List[str]:
        """Extract potential actions from generated response text."""
        # Simple heuristic: look for sentences with action verbs
        action_verbs = ['book', 'search', 'buy', 'send', 'call', 'execute', 'run', 'create', 'update', 'delete']
        actions = []
        sentences = response_text.split('.')
        for sentence in sentences:
            if any(verb in sentence.lower() for verb in action_verbs):
                actions.append(sentence.strip())
        return actions

    def generate_and_validate(
        self,
        prompt: str,
        context: Optional[str] = None,
        domain: Optional[str] = None,
        session_key: Optional[str] = None,
        model_name: str = "gemini-2.5-flash",
    ) -> GuardDecision:
        """Full pipeline: preprocess → Gemini generation → ArmorIQ → validate.

        This is the primary high-level entry point when using GuardlyAI with
        Gemini as the main generation model.  It runs in five stages:

        1. **Preprocessing** (if enabled): Refine the prompt via Gemini and
           compact the context to fit within the token budget.
        2. **Gemini Generation**: Call Gemini with the (possibly refined) prompt
           and (possibly compacted) context to produce the output.
        3. **ArmorIQ Intent Check** (if configured): Verify that Gemini's output
           is aligned with the user's original intent *before* validation.
           Blocks immediately on deflection — the model went off-track.
        4. **Validation Pipeline**: Run the 4-tier cascade
           (Prompt Security → Heuristics → Embedding → HHEM).
        5. **Output**: Return ``GuardDecision`` enriched with preprocessing
           metadata and any ArmorIQ enforcement result.

        The existing ``validate()`` method is **unchanged** — backward-compatible.

        Args:
            prompt: The user prompt to process.
            context: Optional reference context (documents, RAG results, etc.).
                    Stored in the ``ContextManager`` under ``session_key`` and
                    compacted if preprocessing is enabled.
            domain: Optional domain tag (e.g. ``"healthcare"``).
            session_key: Key for the ``ContextManager`` context entry.
                        Defaults to ``domain`` then ``"default"``.
            model_name: Gemini model for generation.
                       Defaults to ``"gemini-2.5-flash"``.

        Returns:
            ``GuardDecision`` with all validation fields plus
            ``preprocessing_metadata`` and (optionally) ``action_enforcement``.

        Raises:
            ImportError: If ``google.generativeai`` is not installed.
            ValueError: If prompt is empty.
            IntentViolationError: If ArmorIQ detects model deflection.
        """
        if not prompt or not isinstance(prompt, str):
            raise ValueError("prompt must be a non-empty string")

        key = session_key or domain or "default"
        preprocessing_meta: dict = {}
        effective_prompt = prompt
        effective_context = context

        # ── Stage 1: Preprocessing ────────────────────────────────────
        if self.preprocessing_enabled:
            try:
                # Analyse & optionally refine the prompt
                analysis = self._analyzer.analyze(prompt)  # type: ignore[attr-defined]
                effective_prompt = analysis.refined_prompt
                preprocessing_meta["prompt_analysis"] = {
                    "intent": analysis.intent.value,
                    "was_refined": analysis.was_refined,
                    "needs_refinement": analysis.needs_refinement,
                    "latency_ms": round(analysis.latency_ms, 2),
                    "mode": analysis.analysis_metadata.get("mode", "unknown"),
                }

                # Extract and store ground truth context
                ground_truth = self._analyzer.extract_ground_truth(analysis)  # type: ignore[attr-defined]
                self._context_mgr.store_ground_truth(key, ground_truth)  # type: ignore[attr-defined]
                gt_snapshot = {
                    "original_prompt": ground_truth.original_prompt,
                    "intent": ground_truth.intent.value,
                    "core_task": ground_truth.core_task,
                    "constraints": ground_truth.constraints,
                    "entities": ground_truth.entities,
                    "domain": ground_truth.domain,
                    "sensitivity_tags": ground_truth.sensitivity_tags,
                    "context_requirements": ground_truth.context_requirements,
                    "created_at": ground_truth.created_at,
                    "confidence": round(ground_truth.confidence, 2),
                }
                preprocessing_meta["ground_truth"] = {
                    "core_task": gt_snapshot["core_task"],
                    "domain": gt_snapshot["domain"],
                    "confidence": gt_snapshot["confidence"],
                    "entities": gt_snapshot["entities"][:5],  # Limit for metadata
                    "sensitivity_tags": gt_snapshot["sensitivity_tags"],
                }
                # Attach full snapshot to decision later for UIs/clients
                preprocessing_meta["_ground_truth_full"] = gt_snapshot

                # Use ground truth as validation context when no explicit context provided
                if not context or not context.strip():
                    gt_parts = []
                    if ground_truth.core_task:
                        gt_parts.append(f"Task: {ground_truth.core_task}")
                    if ground_truth.entities:
                        gt_parts.append(f"Entities: {', '.join(ground_truth.entities)}")
                    if ground_truth.context_requirements:
                        gt_parts.append("\n".join(ground_truth.context_requirements))
                    if ground_truth.constraints:
                        gt_parts.append(f"Constraints: {', '.join(ground_truth.constraints)}")
                    if gt_parts:
                        effective_context = "\n".join(gt_parts)
                        logger.debug(f"Guard: using ground truth as validation context ({len(effective_context)} chars)")

                if context:
                    self._context_mgr.update(key, context)  # type: ignore[attr-defined]
                    entry = self._context_mgr.compact(  # type: ignore[attr-defined]
                        key,
                        prompt=effective_prompt,
                        max_tokens=2048,
                    )
                    if entry:
                        effective_context = entry.content
                        preprocessing_meta["context_compaction"] = {
                            "original_tokens": _estimate_context_tokens(context),
                            "compacted_tokens": entry.token_count,
                            "compacted": entry.compacted,
                        }
            except Exception as e:
                logger.warning(
                    f"Guard: preprocessing failed ({e}), continuing with original prompt/context"
                )
                effective_prompt = prompt

        # ── Stage 2: Gemini Generation ────────────────────────────────
        try:
            import google.generativeai as genai
            import os
            genai.configure(api_key=os.getenv("GOOGLE_API_KEY", ""))
            
            gemini_model = genai.GenerativeModel(model_name)

            generation_prompt = effective_prompt
            if effective_context:
                generation_prompt = (
                    f"Context:\n{effective_context}\n\nQuestion/Task:\n{effective_prompt}"
                )
            
            model_response = None
            max_retries = 2
            
            for attempt in range(max_retries + 1):
                try:
                    model_response = gemini_model.generate_content(generation_prompt)
                    break
                except Exception as e:
                    if ("429" in str(e) or "Quota" in str(e)) and attempt < max_retries:
                        err_str = str(e)
                        match = re.search(r'retry in ([\d\.]+)s', err_str)
                        if match:
                            delay = min(float(match.group(1)) + 1.0, 30.0)
                        else:
                            match_seconds = re.search(r'seconds: (\d+)', err_str)
                            if match_seconds:
                                delay = min(float(match_seconds.group(1)) + 1.0, 30.0)
                            else:
                                delay = 5.0
                        logger.warning(f"Guard: Rate limited (429) during generation. Retrying in {delay:.1f}s (Attempt {attempt+1}/{max_retries})...")
                        time.sleep(delay)
                    else:
                        raise
            
            # Ensure we get a real string, especially when mocked
            output_val = model_response.text if model_response else ""
            output = str(output_val) if output_val is not None else ""
            
            if not output:
                logger.warning("Guard: Gemini returned empty output, using empty string")
            
            preprocessing_meta["generation"] = {
                "model": model_name, 
                "prompt_used": "refined" if effective_prompt != prompt else "original"
            }
        except ImportError:
            raise ImportError(
                "google.generativeai is required for generate_and_validate(). "
                "Install with: pip install google-generativeai"
            )
        except Exception as e:
            logger.error(f"Guard: Gemini generation failed: {e}")
            if "429" in str(e) or "Quota" in str(e):
                return GuardDecision(
                    decision="abstain",
                    risk_score=0.0,
                    confidence=1.0,
                    output="",
                    evidence="Generation failed: Google API Quota exceeded (Rate Limit/429) consistently over multiple retries.",
                    suggested_fix="Check your Google API quota or wait for the rate limit to reset.",
                    validator_results=[],
                    latency_ms=0.0,
                    policy_name=self.policy.name,
                    preprocessing_metadata=preprocessing_meta or None,
                )
            raise

        # ── Stage 3: ArmorIQ Intent Check (post-gen, pre-validation) ──
        # Checks whether Gemini's output is aligned with the stored ground truth
        # task scope — catches model deflection before validation runs.
        enforcement_result: Optional[ActionEnforcementResult] = None
        if self.armoriq is not None:
            try:
                # Use ground truth task if available, otherwise fall back to prompt
                ground_truth_task = None
                if self.preprocessing_enabled:
                    ground_truth_task = self._context_mgr.get_session_task(key)  # type: ignore[attr-defined]

                task_scope = ground_truth_task or prompt
                self.armoriq.enforce(user_task=task_scope, action_plan=output)
                enforcement_result = ActionEnforcementResult(
                    enforced=True,
                    allowed=True,
                    user_task=prompt,
                    action_plan=output[:200],  # truncate for storage
                    reason=None,
                )
                logger.debug("Guard[generate]: ArmorIQ: output aligned with user intent")
            except IntentViolationError as e:
                enforcement_result = ActionEnforcementResult(
                    enforced=True,
                    allowed=False,
                    user_task=prompt,
                    action_plan=output[:200],
                    reason=e.reason,
                )
                logger.warning(
                    f"Guard[generate]: ArmorIQ blocked — model deflected: {e.reason}"
                )
                # Return a block decision immediately — skip validation
                return GuardDecision(
                    decision="block",
                    risk_score=1.0,
                    confidence=1.0,
                    output=output,
                    evidence=f"Model deflected from user intent: {e.reason}",
                    suggested_fix="Rephrase the prompt to reduce ambiguity.",
                    validator_results=[],
                    latency_ms=0.0,
                    policy_name=self.policy.name,
                    action_enforcement=enforcement_result,
                    preprocessing_metadata=preprocessing_meta or None,
                )

        # ── Stage 4: Validation ───────────────────────────────────────
        decision = self.validate(
            prompt=prompt,
            output=output,
            context=effective_context,
            domain=domain,
        )

        # ── Stage 5: Attach preprocessing metadata + enforcement ──────
        updates: dict = {}
        if preprocessing_meta:
            # Promote full ground truth snapshot to top-level decision field for UIs
            gt_full = preprocessing_meta.pop("_ground_truth_full", None)
            if gt_full is not None:
                updates["ground_truth"] = gt_full
            updates["preprocessing_metadata"] = preprocessing_meta
        if enforcement_result is not None:
            updates["action_enforcement"] = enforcement_result
        if updates:
            decision = decision.model_copy(update=updates)

        return decision

    async def generate_and_validate_async(
        self,
        prompt: str,
        context: Optional[str] = None,
        domain: Optional[str] = None,
        session_key: Optional[str] = None,
        model_name: str = "gemini-2.5-flash",
    ) -> GuardDecision:
        """Async wrapper for ``generate_and_validate()``.

        Runs the full pipeline (preprocess → generate → ArmorIQ → validate)
        in a thread executor to avoid blocking the event loop.

        Args:
            prompt: User prompt.
            context: Optional reference context.
            domain: Optional domain tag.
            session_key: Context manager key.
            model_name: Gemini model for generation.

        Returns:
            ``GuardDecision`` — same as ``generate_and_validate()``.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.generate_and_validate(
                prompt, context, domain, session_key, model_name
            ),
        )

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


def _estimate_context_tokens(text: str) -> int:
    """Rough token count estimate for context metadata (4 chars per token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)
