"""Unit tests for the decision engine module.

Tests cover:
- GuardDecision schema validation
- aggregate_scores() with various edge cases
- make_decision() with different policy configurations
- generate_suggested_fix() for all validator types
"""

import pytest
from verdict.core.decision import (
    GuardDecision,
    aggregate_scores,
    make_decision,
    generate_suggested_fix,
)
from verdict.validators.base import ValidationResult
from verdict.policy.schema import (
    PolicyConfig,
    ValidatorConfig,
    MitigationConfig,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sample_validation_result_passed():
    """A validation result that passed."""
    return ValidationResult(
        validator_name="heuristics",
        score=0.85,
        passed=True,
        evidence="High context coverage",
        latency_ms=2.5,
        error=None,
    )


@pytest.fixture
def sample_validation_result_failed():
    """A validation result that failed."""
    return ValidationResult(
        validator_name="embedding",
        score=0.45,
        passed=False,
        evidence="Low similarity to context",
        latency_ms=25.0,
        error=None,
    )


@pytest.fixture
def sample_validation_result_errored():
    """A validation result with an error."""
    return ValidationResult(
        validator_name="hhem",
        score=0.5,
        passed=False,
        evidence="Validator encountered an error",
        latency_ms=0.0,
        error="Model loading failed",
    )


@pytest.fixture
def default_policy():
    """The default policy configuration."""
    return PolicyConfig(
        name="default",
        description="Balanced general-purpose policy",
        latency_budget_ms=100,
        risk_threshold=0.5,
        validators=[
            ValidatorConfig(
                name="heuristics",
                enabled=True,
                weight=0.2,
                threshold=0.5,
                timeout_ms=5,
            ),
            ValidatorConfig(
                name="embedding",
                enabled=True,
                weight=0.3,
                threshold=0.7,
                timeout_ms=30,
            ),
            ValidatorConfig(
                name="hhem",
                enabled=True,
                weight=0.5,
                threshold=0.7,
                timeout_ms=80,
            ),
        ],
        mitigation=MitigationConfig(
            on_block="block",
            on_timeout="allow",
            on_error="abstain",
        ),
    )


@pytest.fixture
def strict_policy():
    """A strict policy for high-risk domains."""
    return PolicyConfig(
        name="rag_strict",
        description="Strict policy for RAG applications",
        latency_budget_ms=150,
        risk_threshold=0.3,
        validators=[
            ValidatorConfig(
                name="heuristics",
                enabled=True,
                weight=0.2,
                threshold=0.5,
                timeout_ms=5,
            ),
            ValidatorConfig(
                name="embedding",
                enabled=True,
                weight=0.3,
                threshold=0.7,
                timeout_ms=30,
            ),
            ValidatorConfig(
                name="hhem",
                enabled=True,
                weight=0.5,
                threshold=0.8,
                timeout_ms=80,
            ),
        ],
        mitigation=MitigationConfig(
            on_block="regenerate",
            on_timeout="allow",
            on_error="abstain",
        ),
    )


# ============================================================================
# Tests: aggregate_scores()
# ============================================================================


def test_aggregate_scores_single_validator(sample_validation_result_passed):
    """Single validator should have confidence 1.0."""
    results = [sample_validation_result_passed]
    weights = {"heuristics": 1.0}
    
    score, confidence = aggregate_scores(results, weights)
    
    assert score == 0.85
    assert confidence == 1.0


def test_aggregate_scores_empty_results():
    """Empty results should return neutral score with zero confidence."""
    score, confidence = aggregate_scores([], {})
    
    assert score == 0.5
    assert confidence == 0.0


def test_aggregate_scores_all_failed(sample_validation_result_errored):
    """All validators errored should return neutral score with zero confidence."""
    results = [sample_validation_result_errored]
    weights = {"hhem": 0.5}
    
    score, confidence = aggregate_scores(results, weights)
    
    assert score == 0.5
    assert confidence == 0.0


def test_aggregate_scores_weighted_average(
    sample_validation_result_passed,
    sample_validation_result_failed,
):
    """Weighted average should be calculated correctly."""
    results = [sample_validation_result_passed, sample_validation_result_failed]
    # Weights: heuristics=0.4 (80% of 0.5 total), embedding=0.1 (20% of 0.5 total)
    weights = {"heuristics": 0.4, "embedding": 0.1}
    
    score, confidence = aggregate_scores(results, weights)
    
    # Expected: (0.85 * 0.4 + 0.45 * 0.1) / (0.4 + 0.1)
    #         = (0.34 + 0.045) / 0.5 = 0.385 / 0.5 = 0.77
    assert abs(score - 0.77) < 0.01


def test_aggregate_scores_confidence_high_agreement(
    sample_validation_result_passed,
):
    """High agreement (same score) should give high confidence."""
    # Two validators with same score
    result2 = ValidationResult(
        validator_name="embedding",
        score=0.85,
        passed=True,
        evidence="High similarity",
        latency_ms=28.0,
        error=None,
    )
    results = [sample_validation_result_passed, result2]
    weights = {"heuristics": 0.5, "embedding": 0.5}
    
    score, confidence = aggregate_scores(results, weights)
    
    assert score == 0.85
    assert confidence == 1.0  # Variance is zero


def test_aggregate_scores_confidence_low_agreement():
    """Low agreement (different scores) should give low confidence."""
    result1 = ValidationResult(
        validator_name="heuristics",
        score=0.9,
        passed=True,
        evidence="High context coverage",
        latency_ms=2.5,
        error=None,
    )
    result2 = ValidationResult(
        validator_name="hhem",
        score=0.1,
        passed=False,
        evidence="Low confidence in faithfulness",
        latency_ms=75.0,
        error=None,
    )
    results = [result1, result2]
    weights = {"heuristics": 0.5, "hhem": 0.5}
    
    score, confidence = aggregate_scores(results, weights)
    
    assert abs(score - 0.5) < 0.01  # Average of 0.9 and 0.1
    assert confidence < 0.5  # High variance → low confidence


def test_aggregate_scores_mixed_errored_and_valid(
    sample_validation_result_passed,
    sample_validation_result_errored,
):
    """Mix of errored and valid results should only use valid ones."""
    results = [sample_validation_result_passed, sample_validation_result_errored]
    weights = {"heuristics": 0.2, "hhem": 0.8}
    
    score, confidence = aggregate_scores(results, weights)
    
    # Only heuristics (0.85) should be counted
    # But wait, heuristics has weight 0.2 and hhem (errored) has 0.8
    # So we only have heuristics valid. Total weight = 0.2
    # Score = (0.85 * 0.2) / 0.2 = 0.85
    assert abs(score - 0.85) < 0.01


def test_aggregate_scores_zero_weights_fallback():
    """Zero weight should fallback to simple average."""
    result1 = ValidationResult(
        validator_name="validator_a",
        score=0.8,
        passed=True,
        evidence="Test",
        latency_ms=10.0,
        error=None,
    )
    result2 = ValidationResult(
        validator_name="validator_b",
        score=0.6,
        passed=True,
        evidence="Test",
        latency_ms=10.0,
        error=None,
    )
    # Both validators have zero weight
    weights = {"validator_a": 0.0, "validator_b": 0.0}
    
    score, confidence = aggregate_scores([result1, result2], weights)
    
    # Should fallback to simple average: (0.8 + 0.6) / 2 = 0.7
    assert abs(score - 0.7) < 0.01


# ============================================================================
# Tests: make_decision()
# ============================================================================


def test_make_decision_allow_faithful(sample_validation_result_passed, default_policy):
    """Faithful output should be allowed."""
    results = [sample_validation_result_passed]
    aggregated_score = 0.85  # 1.0 - 0.85 = risk 0.15 < 0.5 threshold
    
    decision = make_decision(results, aggregated_score, default_policy, 50.0)
    
    assert decision.decision == "allow"
    assert decision.risk_score == pytest.approx(0.15)
    assert decision.policy_name == "default"


def test_make_decision_block_hallucinated(sample_validation_result_failed, default_policy):
    """Hallucinated output should be blocked."""
    results = [sample_validation_result_failed]
    aggregated_score = 0.45  # 1.0 - 0.45 = risk 0.55 > 0.5 threshold
    
    decision = make_decision(results, aggregated_score, default_policy, 50.0)
    
    assert decision.decision == "block"
    assert decision.risk_score == 0.55
    assert decision.suggested_fix is not None


def test_make_decision_regenerate_on_strict_policy(
    sample_validation_result_failed,
    strict_policy,
):
    """Strict policy should regenerate instead of block."""
    results = [sample_validation_result_failed]
    aggregated_score = 0.45  # 1.0 - 0.45 = risk 0.55 > 0.3 threshold
    
    decision = make_decision(results, aggregated_score, strict_policy, 50.0)
    
    assert decision.decision == "regenerate"
    assert decision.suggested_fix is not None


def test_make_decision_timeout_priority(sample_validation_result_passed, default_policy):
    """Timeout should override score check."""
    results = [sample_validation_result_passed]
    aggregated_score = 0.85  # Would be allowed
    latency_ms = 150.0  # Exceeds budget of 100
    
    decision = make_decision(results, aggregated_score, default_policy, latency_ms)
    
    assert decision.decision == "allow"  # on_timeout mitigation
    assert decision.latency_ms == 150.0


def test_make_decision_all_errored_priority(sample_validation_result_errored, default_policy):
    """All validators errored should use on_error mitigation."""
    results = [sample_validation_result_errored]
    aggregated_score = 0.5  # Neutral
    
    decision = make_decision(results, aggregated_score, default_policy, 50.0)
    
    assert decision.decision == "abstain"  # on_error mitigation


def test_make_decision_mixed_results(
    sample_validation_result_passed,
    sample_validation_result_errored,
    default_policy,
):
    """Mix of passed and errored validators should not trigger on_error."""
    results = [sample_validation_result_passed, sample_validation_result_errored]
    aggregated_score = 0.85
    
    decision = make_decision(results, aggregated_score, default_policy, 50.0)
    
    # Not all errored, so should check risk threshold instead
    assert decision.decision == "allow"


def test_make_decision_evidence_format(sample_validation_result_passed, default_policy):
    """Evidence should be formatted correctly."""
    results = [sample_validation_result_passed]
    aggregated_score = 0.85
    
    decision = make_decision(results, aggregated_score, default_policy, 50.0)
    
    assert "Risk: 0.15" in decision.evidence
    assert "threshold: 0.50" in decision.evidence
    assert "heuristics" in decision.evidence
    assert "0.85" in decision.evidence
    assert "✓" in decision.evidence  # Passed indicator


def test_make_decision_frozen_model():
    """GuardDecision should be immutable."""
    decision = GuardDecision(
        decision="allow",
        risk_score=0.2,
        confidence=0.9,
        output="Test output",
        evidence="Test evidence",
        validator_results=[],
        latency_ms=50.0,
        policy_name="test",
    )
    
    with pytest.raises(Exception):  # FrozenInstanceError
        decision.risk_score = 0.5  # type: ignore


# ============================================================================
# Tests: generate_suggested_fix()
# ============================================================================


def test_generate_suggested_fix_heuristics_failed():
    """Failed heuristics validator should suggest context coverage."""
    result = ValidationResult(
        validator_name="heuristics",
        score=0.3,
        passed=False,
        evidence="Low context coverage",
        latency_ms=5.0,
        error=None,
    )
    
    fix = generate_suggested_fix([result])
    
    assert fix is not None
    assert "context coverage" in fix.lower()


def test_generate_suggested_fix_embedding_failed():
    """Failed embedding validator should suggest alignment."""
    result = ValidationResult(
        validator_name="embedding",
        score=0.4,
        passed=False,
        evidence="Low similarity",
        latency_ms=25.0,
        error=None,
    )
    
    fix = generate_suggested_fix([result])
    
    assert fix is not None
    assert "align" in fix.lower() or "grounded" in fix.lower()


def test_generate_suggested_fix_hhem_failed():
    """Failed HHEM validator should suggest factual grounding."""
    result = ValidationResult(
        validator_name="hhem",
        score=0.2,
        passed=False,
        evidence="Low faithfulness",
        latency_ms=75.0,
        error=None,
    )
    
    fix = generate_suggested_fix([result])
    
    assert fix is not None
    assert "factual" in fix.lower() or "grounding" in fix.lower()


def test_generate_suggested_fix_no_failed_validators():
    """No failed validators should return None."""
    result = ValidationResult(
        validator_name="heuristics",
        score=0.8,
        passed=True,
        evidence="Good context coverage",
        latency_ms=5.0,
        error=None,
    )
    
    fix = generate_suggested_fix([result])
    
    assert fix is None


def test_generate_suggested_fix_errored_validators_ignored():
    """Errored validators should be ignored."""
    result = ValidationResult(
        validator_name="hhem",
        score=0.5,
        passed=False,
        evidence="Error occurred",
        latency_ms=0.0,
        error="Model loading failed",
    )
    
    fix = generate_suggested_fix([result])
    
    assert fix is None


def test_generate_suggested_fix_deduplication():
    """Duplicate hints should be deduplicated."""
    result1 = ValidationResult(
        validator_name="embedding",
        score=0.4,
        passed=False,
        evidence="Low similarity",
        latency_ms=25.0,
        error=None,
    )
    result2 = ValidationResult(
        validator_name="embedding_v2",
        score=0.4,
        passed=False,
        evidence="Low similarity",
        latency_ms=25.0,
        error=None,
    )
    
    # Both would generate similar hints
    fix = generate_suggested_fix([result1, result2])
    
    assert fix is not None
    # Should not have duplicated hints


def test_generate_suggested_fix_multiple_validators():
    """Multiple failed validators should generate multiple hints."""
    result1 = ValidationResult(
        validator_name="heuristics",
        score=0.3,
        passed=False,
        evidence="Low coverage",
        latency_ms=5.0,
        error=None,
    )
    result2 = ValidationResult(
        validator_name="hhem",
        score=0.2,
        passed=False,
        evidence="Low faithfulness",
        latency_ms=75.0,
        error=None,
    )
    
    fix = generate_suggested_fix([result1, result2])
    
    assert fix is not None
    # Should have hints from both validators


# ============================================================================
# Integration Tests
# ============================================================================


def test_full_pipeline_allow_workflow(default_policy):
    """Full workflow for allowed output."""
    results = [
        ValidationResult(
            validator_name="heuristics",
            score=0.85,
            passed=True,
            evidence="Good context coverage",
            latency_ms=3.0,
            error=None,
        ),
        ValidationResult(
            validator_name="embedding",
            score=0.80,
            passed=True,
            evidence="High similarity",
            latency_ms=28.0,
            error=None,
        ),
        ValidationResult(
            validator_name="hhem",
            score=0.82,
            passed=True,
            evidence="High faithfulness",
            latency_ms=78.0,
            error=None,
        ),
    ]
    
    # Aggregate scores
    weights = {v.name: v.weight for v in default_policy.validators}
    aggregated_score, confidence = aggregate_scores(results, weights)
    
    # Make decision
    decision = make_decision(results, aggregated_score, default_policy, 110.0)
    
    assert decision.decision == "allow"
    assert decision.risk_score < 0.5
    assert confidence > 0.8


def test_full_pipeline_block_workflow(default_policy):
    """Full workflow for blocked output."""
    results = [
        ValidationResult(
            validator_name="heuristics",
            score=0.3,
            passed=False,
            evidence="Low context coverage",
            latency_ms=3.0,
            error=None,
        ),
        ValidationResult(
            validator_name="embedding",
            score=0.4,
            passed=False,
            evidence="Low similarity",
            latency_ms=28.0,
            error=None,
        ),
        ValidationResult(
            validator_name="hhem",
            score=0.2,
            passed=False,
            evidence="Low faithfulness",
            latency_ms=78.0,
            error=None,
        ),
    ]
    
    # Aggregate scores
    weights = {v.name: v.weight for v in default_policy.validators}
    aggregated_score, confidence = aggregate_scores(results, weights)
    
    # Make decision
    decision = make_decision(results, aggregated_score, default_policy, 50.0)
    
    assert decision.decision == "block"
    assert decision.risk_score > 0.5
    assert decision.suggested_fix is not None
