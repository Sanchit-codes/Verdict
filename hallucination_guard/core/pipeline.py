"""Four-tier validation cascade orchestrator with early-exit optimization.

This module implements the ValidationPipeline class that:
1. Orchestrates validators in tier order (Prompt Security → Heuristics → Embedding → HHEM)
2. Implements early-exit logic to skip validators when decisions are clear
3. Enforces latency budgets and handles timeouts gracefully
4. Aggregates weighted scores using the decision engine
5. Returns final GuardDecision with all metadata

Tier structure:
- Tier 0.5 (Prompt Security): prompt_structure (always passes) → prompt_injection (may block early)
- Tier 1 (Heuristics): score < 0.2 → BLOCK, score > 0.9 → ALLOW
- Tier 2 (Embedding): weighted_avg < 0.3 → BLOCK, > 0.85 → ALLOW
- Tier 3 (HHEM): final decision

Latency enforcement:
- If elapsed time exceeds policy.latency_budget_ms, remaining validators
  marked with timeout error and score set to 0.5 (neutral)
"""

import asyncio
import logging
import time

from hallucination_guard.core.decision import (
    GuardDecision,
    aggregate_scores,
    make_decision,
)
from hallucination_guard.policy.loader import load_policy
from hallucination_guard.policy.schema import PolicyConfig
from hallucination_guard.validators.base import (
    BaseValidator,
    ValidationInput,
    ValidationResult,
)
from hallucination_guard.validators.embedding import EmbeddingValidator
from hallucination_guard.validators.heuristics import HeuristicsValidator
from hallucination_guard.validators.hhem import HHEMValidator
from hallucination_guard.validators.prompt_injection import PromptInjectionValidator
from hallucination_guard.validators.prompt_structure import PromptStructureValidator

logger = logging.getLogger(__name__)


# Mapping of validator names to their implementation classes
VALIDATOR_REGISTRY: dict[str, type[BaseValidator]] = {
    "prompt_structure": PromptStructureValidator,
    "prompt_injection": PromptInjectionValidator,
    "heuristics": HeuristicsValidator,
    "embedding": EmbeddingValidator,
    "hhem": HHEMValidator,
}


class ValidationPipeline:
    """Orchestrates the three-tier validation cascade with early-exit logic.

    Attributes:
        policy: PolicyConfig defining validator configuration and thresholds
        validators: Dict mapping validator names to instantiated validator objects
    """

    def __init__(self, policy: PolicyConfig):
        # NOTE: PolicyConfig is frozen, so any dynamic runtime toggles that
        # affect which validators run should be applied by the caller before
        # constructing ValidationPipeline (e.g. by passing a modified copy of
        # the policy).
        """Initialize pipeline with a policy configuration.

        Loads and instantiates validators based on policy.validators list.
        Validators are only loaded if they are enabled and available
        (is_available() == True).

        Args:
            policy: PolicyConfig with validator configurations and latency budget
        """
        self.policy = policy
        self.validators: dict[str, BaseValidator] = {}

        # Load each enabled validator
        for validator_config in policy.validators:
            if not validator_config.enabled:
                logger.debug(f"Validator '{validator_config.name}' is disabled, skipping")
                continue

            # Get validator class from registry
            ValidatorClass = VALIDATOR_REGISTRY.get(validator_config.name)
            if ValidatorClass is None:
                logger.warning(f"Unknown validator: {validator_config.name}, skipping")
                continue

            # Instantiate validator with config
            try:
                validator = ValidatorClass(
                    {
                        "threshold": validator_config.threshold,
                        "timeout_ms": validator_config.timeout_ms,
                    }
                )

                # Check if validator is available (dependencies loaded, models available, etc.)
                if validator.is_available():
                    self.validators[validator_config.name] = validator
                    logger.debug(f"Loaded validator: {validator_config.name}")
                else:
                    logger.warning(
                        f"Validator '{validator_config.name}' not available "
                        "(dependencies missing or disabled)"
                    )
            except Exception as e:
                logger.error(f"Failed to initialize validator '{validator_config.name}': {e}")

    def run(
        self,
        input: ValidationInput,
    ) -> GuardDecision:
        """Execute the four-tier validation cascade with early-exit logic.

        Runs validators in tier order:
        1. Tier 0.5 (Prompt Security):
           - prompt_structure: Always analyzes, always passes (extracted metadata)
           - prompt_injection: May block early if injection_risk > threshold
        2. Tier 1 (Heuristics): if score < 0.2 or > 0.9, exit early
        3. Tier 2 (Embedding): if weighted_avg < 0.3 or > 0.85, exit early
        4. Tier 3 (HHEM): final decision

        Tier 0.5 behavior:
        - prompt_structure runs first (always passes, analysis only)
        - StructuredPrompt is injected into ValidationInput for downstream validators
        - prompt_injection runs next (may block early if high risk)
        - If injection_risk > (1.0 - threshold), returns block decision immediately

        Enforces latency budget: if elapsed time exceeds policy.latency_budget_ms,
        remaining validators are marked with timeout error.

        Args:
            input: ValidationInput with prompt, output, context, and domain

        Returns:
            GuardDecision with decision, risk_score, evidence, and validator results
        """
        results: list[ValidationResult] = []
        start_time = time.perf_counter()

        # Build weights dict for aggregation (name -> weight from policy)
        weights = {v.name: v.weight for v in self.policy.validators}

        for validator_config in self.policy.validators:
            if not validator_config.enabled:
                continue

            validator = self.validators.get(validator_config.name)
            if validator is None:
                # Validator not loaded (not available or missing)
                logger.debug(f"Validator '{validator_config.name}' not loaded, skipping")
                continue

            # Check if we've exceeded latency budget
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            if elapsed_ms > self.policy.latency_budget_ms:
                # Mark remaining validators with timeout error
                timeout_result = ValidationResult(
                    validator_name=validator_config.name,
                    score=0.5,  # Neutral score
                    passed=False,
                    evidence="Latency budget exceeded",
                    latency_ms=0.0,
                    error="Timeout",
                )
                results.append(timeout_result)
                logger.warning(
                    f"Latency budget exceeded ({elapsed_ms:.2f}ms > "
                    f"{self.policy.latency_budget_ms}ms), "
                    f"skipping validator '{validator_config.name}'"
                )
                continue

            # Run validator with error handling
            logger.debug(f"Pipeline: running validator '{validator_config.name}'...")
            result = self._run_validator(validator, input, validator_config.timeout_ms)
            results.append(result)
            logger.debug(f"Pipeline: '{result.validator_name}' completed with score={result.score:.3f}, latency={result.latency_ms:.1f}ms")

            # Tier 0.5: Inject StructuredPrompt into ValidationInput for downstream use
            if validator_config.name == "prompt_structure":
                if result.metadata and "structured_prompt" in result.metadata:
                    structured_prompt = result.metadata["structured_prompt"]
                    input = input.model_copy(update={"structured_prompt": structured_prompt})

            # Early-exit logic based on tier
            tier_num = self._get_tier_number(validator_config.name)

            # Tier 0.5: Prompt injection early-exit (block if high injection risk)
            if validator_config.name == "prompt_injection":
                if result.error is None:
                    # Score < threshold means high injection risk
                    # Invert: 0.0 = risky, 1.0 = clean
                    injection_risk = 1.0 - result.score
                    if injection_risk > (1.0 - validator_config.threshold):
                        logger.debug(
                            f"Tier 0.5: Prompt injection detected (risk={injection_risk:.2f}), "
                            f"blocking early"
                        )
                        # Return block decision immediately
                        latency_ms = (time.perf_counter() - start_time) * 1000
                        return GuardDecision(
                            decision="block",
                            risk_score=injection_risk,
                            confidence=1.0,
                            output=input.output,
                            evidence=f"Prompt injection detected: {result.evidence}",
                            suggested_fix=None,
                            validator_results=results,
                            latency_ms=latency_ms,
                            policy_name=self.policy.name,
                            prompt_injection_risk=injection_risk,
                        )

            if tier_num == 1:
                # Tier 1 early-exit: score < 0.2 (clearly bad) or > 0.9 (clearly good)
                if result.error is None:
                    if result.score < 0.2:
                        logger.debug("Tier 1: Clear block (score < 0.2), exiting early")
                        break
                    elif result.score > 0.9:
                        logger.debug("Tier 1: Clear allow (score > 0.9), exiting early")
                        break

            elif tier_num == 2:
                # Tier 2 early-exit: weighted avg < 0.3 or > 0.85
                if result.error is None:
                    aggregated, _ = aggregate_scores(results, weights)
                    if aggregated < 0.3:
                        logger.debug("Tier 2: Clear block (weighted avg < 0.3), exiting early")
                        break
                    elif aggregated > 0.85:
                        logger.debug("Tier 2: Clear allow (weighted avg > 0.85), exiting early")
                        break

        # Calculate final latency
        latency_ms = (time.perf_counter() - start_time) * 1000

        # Aggregate scores and make final decision
        aggregated_score, _ = aggregate_scores(results, weights)

        decision = make_decision(
            results=results,
            aggregated_score=aggregated_score,
            policy=self.policy,
            latency_ms=latency_ms,
        )

        # Fill in output field and return
        return decision.model_copy(update={"output": input.output})

    async def run_async(
        self,
        input: ValidationInput,
    ) -> GuardDecision:
        """Async wrapper around run() using asyncio.to_thread.

        Allows non-blocking execution in async contexts. Uses asyncio.to_thread
        to run the synchronous pipeline in a thread pool.

        Args:
            input: ValidationInput with prompt, output, context, and domain

        Returns:
            GuardDecision with decision, risk_score, evidence, and validator results
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.run, input)

    @staticmethod
    def _run_validator(
        validator: BaseValidator,
        input: ValidationInput,
        timeout_ms: int,
    ) -> ValidationResult:
        """Run a single validator with error handling and timeout tracking.

        Catches exceptions and returns neutral ValidationResult on error.
        Logs warnings if validator latency exceeds timeout_ms.

        Args:
            validator: BaseValidator instance to run
            input: ValidationInput to validate
            timeout_ms: Expected timeout for this validator

        Returns:
            ValidationResult with score, evidence, and optional error field
        """
        try:
            result = validator.validate(input)

            # Log warning if latency exceeded timeout
            if result.latency_ms > timeout_ms:
                logger.warning(
                    f"Validator '{result.validator_name}' exceeded timeout: "
                    f"{result.latency_ms:.2f}ms > {timeout_ms}ms"
                )

            return result
        except Exception as e:
            # Graceful degradation: log error and return neutral score
            validator_name = validator.__class__.__name__.replace("Validator", "").lower()
            tier = ValidationPipeline._get_tier_number(validator_name)

            logger.error(
                f"Validator '{validator.__class__.__name__}' (tier={tier}) "
                f"failed with {type(e).__name__}: {e} | "
                f"Input context={input.context[:100] if input.context else 'None'}... | "
                f"Output length={len(input.output) if input.output else 0} chars",
                exc_info=True,
            )

            return ValidationResult(
                validator_name=validator_name,
                score=0.5,  # Neutral score
                passed=False,
                evidence="Validator failed, returning neutral score",
                latency_ms=0.0,
                error=str(e),
            )

    @staticmethod
    def _get_tier_number(validator_name: str) -> int:
        """Get the tier number for a validator (0.5 = prompt security, 1 = heuristics, 2 = embedding, 3 = hhem).

        Args:
            validator_name: Name of the validator (e.g., "prompt_structure", "prompt_injection", "heuristics", "embedding", "hhem")

        Returns:
            Tier number (0, 1, 2, or 3)
        """
        tier_map = {
            "prompt_structure": 0,
            "prompt_injection": 0,
            "heuristics": 1,
            "embedding": 2,
            "hhem": 3,
        }
        return tier_map.get(validator_name, 0)


def create_pipeline(policy: str | PolicyConfig) -> ValidationPipeline:
    """Backwards-compatible helper, kept for existing callers.

    New code should prefer constructing ValidationPipeline directly or
    extending it when advanced control (e.g. runtime validator toggles)
    is required.
    """
    """Create a ValidationPipeline with the specified policy.
    
    Convenience function to load a policy by name or use an existing PolicyConfig,
    then create and return a ValidationPipeline.
    
    Args:
        policy: Policy name (e.g., "default", "rag_strict"), file path, or PolicyConfig object
    
    Returns:
        Initialized ValidationPipeline ready for validation
    
    Raises:
        PolicyLoadError: If policy cannot be loaded (file not found, invalid YAML, etc.)
    """
    if isinstance(policy, str):
        policy_config = load_policy(policy)
    else:
        policy_config = policy

    return ValidationPipeline(policy_config)
