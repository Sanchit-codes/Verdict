"""Unit tests for Guard class and exception classes."""

import os
import pytest

from hallucination_guard.core.exceptions import (
    HallucinationBlockedError,
    HallucinationGuardError,
    PolicyLoadError,
    ValidationTimeoutError,
)
from hallucination_guard.core.guard import Guard
from hallucination_guard.policy.schema import PolicyConfig


class TestExceptions:
    """Test custom exception classes."""

    def test_hallucination_guard_error_base(self):
        """Test base exception can be raised and caught."""
        with pytest.raises(HallucinationGuardError):
            raise HallucinationGuardError("Test error")

    def test_hallucination_blocked_error_attributes(self):
        """Test HallucinationBlockedError stores decision metadata."""
        evidence = "Low context overlap"
        risk_score = 0.85
        decision = "block"

        error = HallucinationBlockedError(
            evidence=evidence,
            risk_score=risk_score,
            decision=decision,
        )

        assert error.evidence == evidence
        assert error.risk_score == risk_score
        assert error.decision == decision
        assert str(error) == f"Output blocked by validation (risk={risk_score:.2f})"

    def test_hallucination_blocked_error_custom_message(self):
        """Test HallucinationBlockedError accepts custom message."""
        custom_msg = "Custom block message"
        error = HallucinationBlockedError(
            evidence="Low overlap",
            risk_score=0.9,
            message=custom_msg,
        )
        assert str(error) == custom_msg

    def test_validation_timeout_error_attributes(self):
        """Test ValidationTimeoutError stores timing information."""
        latency_ms = 150.5
        budget_ms = 100.0

        error = ValidationTimeoutError(
            latency_ms=latency_ms,
            budget_ms=budget_ms,
        )

        assert error.latency_ms == latency_ms
        assert error.budget_ms == budget_ms
        assert str(error) == (
            f"Validation exceeded latency budget: "
            f"{latency_ms:.2f}ms > {budget_ms}ms"
        )

    def test_validation_timeout_error_custom_message(self):
        """Test ValidationTimeoutError accepts custom message."""
        custom_msg = "Custom timeout message"
        error = ValidationTimeoutError(
            latency_ms=150.0,
            budget_ms=100.0,
            message=custom_msg,
        )
        assert str(error) == custom_msg

    def test_policy_load_error_attributes(self):
        """Test PolicyLoadError stores policy and reason."""
        policy_name = "missing_policy"
        reason = "File not found"

        error = PolicyLoadError(
            policy_name=policy_name,
            reason=reason,
        )

        assert error.policy_name == policy_name
        assert error.reason == reason
        assert str(error) == f"Failed to load policy '{policy_name}': {reason}"

    def test_policy_load_error_custom_message(self):
        """Test PolicyLoadError accepts custom message."""
        custom_msg = "Custom policy error"
        error = PolicyLoadError(
            policy_name="invalid",
            reason="Invalid YAML",
            message=custom_msg,
        )
        assert str(error) == custom_msg

    def test_exception_inheritance(self):
        """Test all exceptions inherit from HallucinationGuardError."""
        assert issubclass(HallucinationBlockedError, HallucinationGuardError)
        assert issubclass(ValidationTimeoutError, HallucinationGuardError)
        assert issubclass(PolicyLoadError, HallucinationGuardError)


class TestGuardInitialization:
    """Test Guard.__init__() with different policy inputs."""

    def test_guard_init_with_policy_name(self):
        """Test Guard initializes with policy name."""
        guard = Guard(policy="default")

        assert guard.policy.name == "default"
        assert guard.pipeline is not None
        assert isinstance(guard.trace_enabled, bool)

    def test_guard_init_with_policy_path(self):
        """Test Guard initializes with policy file path."""
        policy_path = "policies/default.yaml"
        guard = Guard(policy=policy_path)

        assert guard.policy.name == "default"
        assert guard.pipeline is not None

    def test_guard_init_with_policy_config(self):
        """Test Guard initializes with PolicyConfig object."""
        # Load a policy first
        guard1 = Guard(policy="default")
        policy_config = guard1.policy

        # Create another Guard with that config
        guard2 = Guard(policy=policy_config)

        assert guard2.policy == policy_config
        assert guard2.pipeline is not None

    def test_guard_init_with_invalid_policy_name(self):
        """Test Guard raises PolicyLoadError for invalid policy name."""
        with pytest.raises(PolicyLoadError) as exc_info:
            Guard(policy="nonexistent_policy_xyz")

        assert "nonexistent_policy_xyz" in str(exc_info.value)

    def test_guard_init_thinking_callback(self):
        """Test Guard initializes with thinking_callback."""
        events = []
        def cb(msg: str):
            events.append(msg)
            
        guard = Guard(policy="default", thinking_callback=cb)
        assert guard._thinking_cb is cb
        assert guard.pipeline._thinking_cb is cb

    def test_guard_init_with_invalid_policy_type(self):
        """Test Guard raises error for invalid policy type."""
        with pytest.raises((PolicyLoadError, ValueError)):
            Guard(policy=12345)  # type: ignore

    def test_guard_init_trace_enabled_default(self):
        """Test Guard trace_enabled defaults based on env var."""
        # Without LANGFUSE_PUBLIC_KEY
        old_key = os.environ.pop("LANGFUSE_PUBLIC_KEY", None)
        try:
            guard = Guard(policy="default", trace_enabled=None)
            assert guard.trace_enabled is False
        finally:
            if old_key:
                os.environ["LANGFUSE_PUBLIC_KEY"] = old_key

    def test_guard_init_trace_enabled_explicit(self):
        """Test Guard trace_enabled respects explicit argument."""
        guard_true = Guard(policy="default", trace_enabled=True)
        assert guard_true.trace_enabled is True

        guard_false = Guard(policy="default", trace_enabled=False)
        assert guard_false.trace_enabled is False


class TestGuardValidate:
    """Test Guard.validate() method."""

    @pytest.fixture
    def guard(self):
        """Fixture providing a Guard instance."""
        return Guard(policy="default", trace_enabled=False)

    def test_validate_returns_guard_decision(self, guard):
        """Test validate() returns a GuardDecision object."""
        decision = guard.validate(
            prompt="What is AI?",
            output="AI is artificial intelligence.",
            context="AI stands for artificial intelligence.",
        )

        assert decision is not None
        assert hasattr(decision, "decision")
        assert hasattr(decision, "risk_score")
        assert hasattr(decision, "confidence")
        assert hasattr(decision, "output")
        assert hasattr(decision, "evidence")
        assert hasattr(decision, "validator_results")
        assert hasattr(decision, "latency_ms")
        assert hasattr(decision, "policy_name")

    def test_validate_decision_field_values(self, guard):
        """Test validate() decision field has expected values."""
        decision = guard.validate(
            prompt="What is Python?",
            output="Python is a programming language.",
            context="Python is a popular programming language.",
        )

        # Decision should be one of allowed values
        assert decision.decision in ("allow", "block", "regenerate", "abstain")

    def test_validate_risk_score_range(self, guard):
        """Test validate() risk_score is in valid range."""
        decision = guard.validate(
            prompt="What is ML?",
            output="ML stands for machine learning.",
            context="Machine learning is a subset of AI.",
        )

        assert 0.0 <= decision.risk_score <= 1.0

    def test_validate_confidence_range(self, guard):
        """Test validate() confidence is in valid range."""
        decision = guard.validate(
            prompt="What is data science?",
            output="Data science uses data to extract insights.",
            context="Data science is an interdisciplinary field.",
        )

        assert 0.0 <= decision.confidence <= 1.0

    def test_validate_latency_ms_positive(self, guard):
        """Test validate() latency_ms is non-negative."""
        decision = guard.validate(
            prompt="What is AI?",
            output="AI is artificial intelligence.",
            context="AI is a field of computer science.",
        )

        assert decision.latency_ms >= 0.0

    def test_validate_policy_name_matches(self, guard):
        """Test validate() decision includes correct policy name."""
        decision = guard.validate(
            prompt="Test",
            output="Test output",
            context="Test context",
        )

        assert decision.policy_name == "default"

    def test_validate_output_field_matches_input(self, guard):
        """Test validate() output field matches input."""
        output_text = "This is the validated output."
        decision = guard.validate(
            prompt="Test prompt",
            output=output_text,
            context="Test context",
        )

        assert decision.output == output_text

    def test_validate_with_no_context(self, guard):
        """Test validate() works without context."""
        decision = guard.validate(
            prompt="What is AI?",
            output="AI is artificial intelligence.",
        )

        assert decision is not None
        assert decision.decision in ("allow", "block", "regenerate", "abstain")

    def test_validate_with_domain(self, guard):
        """Test validate() accepts domain metadata."""
        decision = guard.validate(
            prompt="What is treatment?",
            output="Treatment is a medical intervention.",
            context="Medicine involves various treatments.",
            domain="healthcare",
        )

        assert decision is not None

    def test_validate_empty_prompt_raises_error(self, guard):
        """Test validate() raises ValueError for empty prompt."""
        with pytest.raises(ValueError):
            guard.validate(
                prompt="",
                output="Some output",
            )

    def test_validate_empty_output_raises_error(self, guard):
        """Test validate() raises ValueError for empty output."""
        with pytest.raises(ValueError):
            guard.validate(
                prompt="Some prompt",
                output="",
            )

    def test_validate_none_prompt_raises_error(self, guard):
        """Test validate() raises ValueError for None prompt."""
        with pytest.raises(ValueError):
            guard.validate(
                prompt=None,  # type: ignore
                output="Some output",
            )

    def test_validate_none_output_raises_error(self, guard):
        """Test validate() raises ValueError for None output."""
        with pytest.raises(ValueError):
            guard.validate(
                prompt="Some prompt",
                output=None,  # type: ignore
            )

    def test_validate_does_not_auto_raise_on_block(self, guard):
        """Test validate() does NOT auto-raise HallucinationBlockedError."""
        # Even with a hallucinated output, validate() should return normally
        # User checks decision.decision and raises manually if needed
        decision = guard.validate(
            prompt="What is the capital of France?",
            output="The capital of France is Tokyo.",  # Clearly wrong
            context="France is a country in Europe. Its capital is Paris.",
        )

        # Should return normally, decision checking is user's responsibility
        assert decision is not None
        # The decision will likely be "block", but that's up to the validators
        assert decision.decision in ("allow", "block", "regenerate", "abstain")


class TestGuardValidateAsync:
    """Test Guard.validate_async() method."""

    @pytest.fixture
    def guard(self):
        """Fixture providing a Guard instance."""
        return Guard(policy="default", trace_enabled=False)

    @pytest.mark.asyncio
    async def test_validate_async_returns_decision(self, guard):
        """Test validate_async() returns a GuardDecision."""
        decision = await guard.validate_async(
            prompt="What is Python?",
            output="Python is a programming language.",
            context="Python is popular.",
        )

        assert decision is not None
        assert decision.decision in ("allow", "block", "regenerate", "abstain")

    @pytest.mark.asyncio
    async def test_validate_async_raises_on_empty_prompt(self, guard):
        """Test validate_async() raises ValueError for empty prompt."""
        with pytest.raises(ValueError):
            await guard.validate_async(
                prompt="",
                output="Some output",
            )

    @pytest.mark.asyncio
    async def test_validate_async_with_context(self, guard):
        """Test validate_async() works with context."""
        decision = await guard.validate_async(
            prompt="What is AI?",
            output="AI is artificial intelligence.",
            context="AI is a field of computer science.",
        )

        assert decision is not None

    @pytest.mark.asyncio
    async def test_validate_async_with_domain(self, guard):
        """Test validate_async() accepts domain metadata."""
        decision = await guard.validate_async(
            prompt="Question",
            output="Answer",
            context="Context",
            domain="healthcare",
        )

        assert decision is not None


class TestGuardMultiplePolicies:
    """Test Guard with different policy configurations."""

    def test_guard_with_different_policies(self):
        """Test Guard can be initialized with different policies."""
        policies = ["default", "rag_strict", "chatbot"]

        guards = [Guard(policy=p, trace_enabled=False) for p in policies]

        for guard, policy_name in zip(guards, policies):
            assert guard.policy.name == policy_name

    def test_guards_are_independent(self):
        """Test multiple Guard instances don't share state."""
        guard1 = Guard(policy="default", trace_enabled=False)
        guard2 = Guard(policy="rag_strict", trace_enabled=False)

        assert guard1.policy.name != guard2.policy.name
        assert guard1.pipeline is not guard2.pipeline


class TestTraceExport:
    """Test trace export integration in Guard.validate()."""

    def test_trace_export_does_not_crash_validation(self):
        """Test that trace export failures don't crash validation."""
        guard = Guard(policy="default", trace_enabled=True)

        decision = guard.validate(
            prompt="What is AI?",
            output="AI is artificial intelligence.",
            context="AI stands for artificial intelligence.",
        )

        # Validation should still succeed even if trace export has issues
        assert decision is not None
        assert isinstance(decision.decision, str)
        assert decision.decision in ("allow", "block", "regenerate", "abstain")

    def test_validate_with_trace_disabled(self):
        """Test validate() works with trace_enabled=False."""
        guard = Guard(policy="default", trace_enabled=False)

        decision = guard.validate(
            prompt="What is Python?",
            output="Python is a programming language.",
            context="Python is popular.",
        )

        assert decision is not None
        assert hasattr(decision, "decision")

    def test_validate_and_check_decision_fields(self):
        """Smoke test: validate() returns complete GuardDecision."""
        guard = Guard(policy="default", trace_enabled=False)

        decision = guard.validate(
            prompt="What is ML?",
            output="ML stands for machine learning.",
            context="Machine learning is a subset of AI.",
            domain="test",
        )

        # Verify all required fields are present
        assert decision.decision in ("allow", "block", "regenerate", "abstain")
        assert 0.0 <= decision.risk_score <= 1.0
        assert 0.0 <= decision.confidence <= 1.0
        assert decision.output is not None
        assert decision.evidence is not None
        assert decision.validator_results is not None
        assert decision.latency_ms > 0.0
        assert decision.policy_name is not None

    def test_planning_callback_emits_in_validate(self):
        """Test that thinking_callback is called during validate()."""
        events = []
        def cb(msg: str):
            events.append(msg)
            
        guard = Guard(policy="default", trace_enabled=False, thinking_callback=cb)
        
        decision = guard.validate(
            prompt="What is ML?",
            output="ML stands for machine learning.",
            context="Machine learning is a subset of AI.",
            domain="test",
        )
        
        assert len(events) > 0
        assert any("Running " in event for event in events)
        assert any("Final Decision:" in event for event in events)

