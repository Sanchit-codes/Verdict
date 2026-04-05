"""Score aggregation and decision mapping for the validation pipeline.

This module implements the decision engine that:
1. Aggregates weighted scores from multiple validators
2. Calculates confidence based on validator agreement
3. Maps aggregated scores to allow/block/regenerate/abstain decisions
4. Generates evidence strings and suggested fixes for failed validators
5. Records optional ArmorIQ action enforcement results in the decision
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

from hallucination_guard.validators.base import ValidationResult
from hallucination_guard.policy.schema import PolicyConfig


class ActionEnforcementResult(BaseModel):
    """Immutable result from an ArmorIQ action enforcement check.

    Attached to GuardDecision when ArmorIQ enforcement is configured and
    an action_plan is provided. Enables callers to inspect intent alignment
    results alongside text validation results.

    Attributes:
        enforced: Whether enforcement actually ran (False if ArmorIQ was skipped).
        allowed:  Whether the action was permitted (True = safe to execute).
        user_task:   The declared task scope that was checked against.
        action_plan: The action that was evaluated.
        reason:   Why an action was blocked (None if allowed).
    """

    enforced: bool = Field(description="Whether ArmorIQ enforcement actually ran")
    allowed: bool = Field(description="Whether the action was permitted")
    user_task: Optional[str] = Field(default=None, description="Declared task scope")
    action_plan: Optional[str] = Field(default=None, description="The action that was evaluated")
    reason: Optional[str] = Field(default=None, description="Violation reason if blocked")

    model_config = {"frozen": True}


class GuardDecision(BaseModel):
    """Immutable decision result from the validation pipeline.
    
    Attributes:
        decision: Action to take (allow, block, regenerate, abstain)
        risk_score: Overall risk score in [0.0, 1.0] where 1.0 = maximum risk
        confidence: Confidence in decision in [0.0, 1.0] based on validator agreement
        output: The validated output (same as input unless modified)
        evidence: Human-readable explanation of the decision
        suggested_fix: Hint for regeneration (if decision == "regenerate")
        validator_results: Individual validation results from all tiers
        latency_ms: Total pipeline execution time in milliseconds
        policy_name: Name of the policy used for decision making
        prompt_injection_risk: Pre-computed prompt injection risk in [0.0, 1.0]
        prompt_security_metadata: Additional prompt security analysis metadata
    """
    
    decision: Literal["allow", "block", "regenerate", "abstain"]
    risk_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    output: str
    evidence: str
    suggested_fix: Optional[str] = None
    validator_results: list[ValidationResult]
    latency_ms: float = Field(ge=0.0)
    policy_name: str
    prompt_injection_risk: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Pre-computed prompt injection risk from security analysis in [0.0, 1.0]",
    )
    prompt_security_metadata: dict[str, str | int | float | bool] = Field(
        default_factory=dict,
        description="Additional prompt security analysis metadata (patterns, intent, sensitivity)",
    )
    # Preprocessing metadata (prompt analysis + context compaction stats)
    preprocessing_metadata: Optional[dict] = Field(
        default=None,
        description=(
            "Preprocessing results attached when Guard.generate_and_validate() is used. "
            "Includes prompt analysis (intent, was_refined) and context compaction stats."
        ),
    )
    # ArmorIQ action enforcement result (None when ArmorIQ is not used)
    action_enforcement: Optional[ActionEnforcementResult] = Field(
        default=None,
        description=(
            "ArmorIQ intent enforcement result. None when no action_plan was provided "
            "or ArmorIQ is not configured."
        ),
    )
    # Optional model thinking and ground truth snapshots (for demos/UIs)
    thinking: Optional[dict] = Field(
        default=None,
        description=(
            "Optional model thinking / reasoning metadata attached by high-level "
            "pipelines for UI/debugging purposes."
        ),
    )
    ground_truth: Optional[dict] = Field(
        default=None,
        description=(
            "Optional ground truth snapshot attached by preprocessing layers for "
            "UI/debugging purposes. Mirrors GroundTruthContext in a JSON-safe form."
        ),
    )

    model_config = {"frozen": True}


def aggregate_scores(
    results: list[ValidationResult],
    weights: dict[str, float],
) -> tuple[float, float]:
    """Aggregate weighted validator scores with confidence calculation.
    
    Implements weighted average aggregation with handling for failed/errored validators.
    Confidence is calculated as the standard deviation of normalized scores (lower std
    = higher confidence in the aggregated decision).
    
    Args:
        results: List of ValidationResult objects from validators
        weights: Mapping of validator_name -> weight (should sum to ~1.0)
    
    Returns:
        Tuple of (aggregated_score, confidence) where:
        - aggregated_score: Weighted average in [0.0, 1.0] (1.0 = faithful)
        - confidence: Agreement level in [0.0, 1.0] (1.0 = all validators agree)
    
    Edge cases:
        - All validators failed (no valid scores): returns (0.5, 0.0)
        - Single validator: returns (score, 1.0) for that validator
        - Mix of failed/succeeded: only uses succeeded validators in aggregation
    """
    if not results:
        return 0.5, 0.0
    
    # Filter to only successful results (no errors)
    valid_results = [r for r in results if r.error is None]
    
    if not valid_results:
        # All validators failed—return neutral score with zero confidence
        return 0.5, 0.0
    
    # Calculate weighted average
    total_weight = 0.0
    weighted_sum = 0.0
    
    for result in valid_results:
        weight = weights.get(result.validator_name, 0.0)
        if weight > 0:
            weighted_sum += result.score * weight
            total_weight += weight
    
    if total_weight == 0:
        # No valid weights—fallback to simple average
        aggregated_score = sum(r.score for r in valid_results) / len(valid_results)
    else:
        # Normalize by total weight
        aggregated_score = weighted_sum / total_weight
    
    # Calculate confidence based on agreement (lower variance = higher confidence)
    if len(valid_results) == 1:
        # Single validator always has perfect confidence
        confidence = 1.0
    else:
        # Calculate normalized variance as disagreement metric
        mean_score = aggregated_score
        variance = sum(
            (r.score - mean_score) ** 2 for r in valid_results
        ) / len(valid_results)
        
        # Map variance [0, 0.25] to confidence [1.0, 0.0]
        # Variance of 0.25 (scores ranging 0.0 to 1.0) = zero confidence
        max_variance = 0.25
        confidence = max(0.0, 1.0 - (variance / max_variance))
    
    return aggregated_score, confidence


def make_decision(
    results: list[ValidationResult],
    aggregated_score: float,
    policy: PolicyConfig,
    latency_ms: float,
) -> GuardDecision:
    """Map aggregated score to allow/block/regenerate/abstain decision.
    
    Implements decision priority logic:
    1. Check for timeout (latency exceeded) → use on_timeout mitigation
    2. Check for all validators errored → use on_error mitigation
    3. Check risk threshold (risk_score > threshold) → use on_block mitigation
    4. Otherwise → allow
    
    Args:
        results: List of ValidationResult from validators
        aggregated_score: Weighted average score from aggregate_scores()
        policy: PolicyConfig with thresholds and mitigation strategies
        latency_ms: Total pipeline execution time
    
    Returns:
        GuardDecision with decision, risk_score, evidence, and suggested_fix
    """
    # Calculate risk score (inverted: 1.0 = maximum risk)
    risk_score = 1.0 - aggregated_score
    
    # Calculate confidence
    _, confidence = aggregate_scores(
        results,
        {v.name: v.weight for v in policy.validators}
    )
    
    # Determine decision based on priority
    decision: Literal["allow", "block", "regenerate", "abstain"]
    
    # Priority 1: Check timeout
    if latency_ms > policy.latency_budget_ms:
        decision = policy.mitigation.on_timeout
    
    # Priority 2: Check all validators errored
    elif all(r.error is not None for r in results):
        decision = policy.mitigation.on_error
    
    # Priority 3: Check risk threshold (risk_score inverted: high risk = high value)
    elif risk_score > policy.risk_threshold:
        decision = policy.mitigation.on_block
    
    # Priority 4: Default allow
    else:
        decision = "allow"
    
    # Generate evidence string
    evidence = _format_evidence(results, risk_score, policy.risk_threshold)
    
    # Generate suggested fix if needed
    suggested_fix = None
    if decision in ("regenerate", "block"):
        suggested_fix = generate_suggested_fix(results)
    
    return GuardDecision(
        decision=decision,
        risk_score=risk_score,
        confidence=confidence,
        output="",  # Will be filled by caller
        evidence=evidence,
        suggested_fix=suggested_fix,
        validator_results=results,
        latency_ms=latency_ms,
        policy_name=policy.name,
    )


def generate_suggested_fix(results: list[ValidationResult]) -> Optional[str]:
    """Extract hints from failed validators to help regenerate output.
    
    Analyzes validator evidence to suggest improvements:
    - Heuristics: "Low context coverage—provide more relevant details"
    - Embedding: "Output differs from context—align with retrieved documents"
    - HHEM: "Lacks factual grounding—cite specific sources"
    
    Args:
        results: List of ValidationResult objects
    
    Returns:
        Suggested fix string, or None if no clear hint available
    """
    hints = []
    
    for result in results:
        if result.error is not None:
            # Skip errored validators
            continue
        
        if not result.passed:
            # Extract hint based on validator name
            if "heuristic" in result.validator_name.lower():
                hints.append(
                    "Increase context coverage: include more specific details from the "
                    "reference material"
                )
            elif "embedding" in result.validator_name.lower():
                hints.append(
                    "Align with context: ensure output is grounded in the provided "
                    "documents"
                )
            elif "hhem" in result.validator_name.lower():
                hints.append(
                    "Add factual grounding: cite specific sources or provide "
                    "verifiable evidence"
                )
    
    if not hints:
        return None
    
    # Return deduplicated hints
    unique_hints = list(dict.fromkeys(hints))
    return "\n- ".join([""] + unique_hints) if unique_hints else None


def _format_evidence(
    results: list[ValidationResult],
    risk_score: float,
    risk_threshold: float,
) -> str:
    """Format evidence string from validation results.
    
    Args:
        results: List of ValidationResult objects
        risk_score: Calculated risk score
        risk_threshold: Policy risk threshold
    
    Returns:
        Formatted evidence string
    """
    lines = [f"Risk: {risk_score:.2f} (threshold: {risk_threshold:.2f})"]
    
    for result in results:
        status = "✓" if result.passed else "✗"
        if result.error:
            status = "⚠"
        lines.append(f"- {result.validator_name}: {result.score:.2f} {status}")
    
    return "\n".join(lines)
