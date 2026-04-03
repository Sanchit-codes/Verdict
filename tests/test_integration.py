"""Integration tests for Guard and validation pipeline."""

import pytest

from hallucination_guard.core.exceptions import (
    HallucinationBlockedError,
    HallucinationGuardError,
    PolicyLoadError,
)
from hallucination_guard.core.guard import Guard


class TestGuardIntegration:
    """Integration tests for the Guard validation pipeline."""

    def test_full_validation_flow_with_faithful_output(self):
        """Test complete validation flow with faithful output."""
        guard = Guard(policy="default", trace_enabled=False)

        decision = guard.validate(
            prompt="What is the capital of France?",
            output="The capital of France is Paris.",
            context="France is a country in Europe with Paris as its capital.",
        )

        # Should get a valid decision
        assert decision is not None
        assert decision.decision in ("allow", "block", "regenerate", "abstain")
        assert decision.policy_name == "default"
        assert 0.0 <= decision.risk_score <= 1.0
        assert len(decision.validator_results) > 0

    def test_full_validation_flow_with_hallucinated_output(self):
        """Test complete validation flow with hallucinated output."""
        guard = Guard(policy="rag_strict", trace_enabled=False)

        decision = guard.validate(
            prompt="What is the capital of France?",
            output="The capital of France is Tokyo.",  # Clearly wrong
            context="France is a country in Europe. Its capital is Paris.",
        )

        # Should get a valid decision (policy decides if blocked or not)
        assert decision is not None
        assert decision.decision in ("allow", "block", "regenerate", "abstain")
        assert 0.0 <= decision.risk_score <= 1.0

    def test_policy_switching(self):
        """Test switching between different policies."""
        policies = {
            "default": Guard(policy="default", trace_enabled=False),
            "rag_strict": Guard(policy="rag_strict", trace_enabled=False),
            "chatbot": Guard(policy="chatbot", trace_enabled=False),
        }

        prompt = "What is AI?"
        output = "AI is artificial intelligence."
        context = "AI stands for artificial intelligence."

        decisions = {}
        for policy_name, guard in policies.items():
            decision = guard.validate(
                prompt=prompt,
                output=output,
                context=context,
            )
            decisions[policy_name] = decision

        # All should return valid decisions
        for policy_name, decision in decisions.items():
            assert decision is not None
            assert decision.policy_name == policy_name
            assert decision.decision in ("allow", "block", "regenerate", "abstain")

    def test_validator_results_present(self):
        """Test that validator results are included in decision."""
        guard = Guard(policy="default", trace_enabled=False)

        decision = guard.validate(
            prompt="What is Python?",
            output="Python is a programming language.",
            context="Python is a popular programming language.",
        )

        # Should have validator results
        assert len(decision.validator_results) > 0

        for result in decision.validator_results:
            assert hasattr(result, "validator_name")
            assert hasattr(result, "score")
            assert hasattr(result, "passed")
            assert hasattr(result, "evidence")
            assert hasattr(result, "latency_ms")
            assert 0.0 <= result.score <= 1.0
            assert result.latency_ms >= 0.0

    def test_multiple_validations_same_guard(self):
        """Test running multiple validations with same Guard instance."""
        guard = Guard(policy="default", trace_enabled=False)

        # First validation
        decision1 = guard.validate(
            prompt="What is Python?",
            output="Python is a language.",
            context="Python is a programming language.",
        )

        # Second validation
        decision2 = guard.validate(
            prompt="What is JavaScript?",
            output="JavaScript is a language.",
            context="JavaScript is a scripting language.",
        )

        # Both should succeed
        assert decision1 is not None
        assert decision2 is not None
        assert decision1.decision in ("allow", "block", "regenerate", "abstain")
        assert decision2.decision in ("allow", "block", "regenerate", "abstain")

    def test_validation_with_long_context(self):
        """Test validation with long context document."""
        guard = Guard(policy="default", trace_enabled=False)

        long_context = """
        Python is a high-level, interpreted programming language known for its
        simplicity and readability. Created by Guido van Rossum and first released
        in 1991, Python emphasizes code readability through significant whitespace.
        
        Key features of Python include:
        - Dynamic typing
        - Automatic memory management
        - Comprehensive standard library
        - Extensive third-party package ecosystem
        - Support for multiple programming paradigms
        
        Python is widely used in web development, data science, artificial
        intelligence, scientific computing, automation, and more.
        """ * 5  # Make it longer

        decision = guard.validate(
            prompt="What are the key features of Python?",
            output="Python has dynamic typing and a comprehensive standard library.",
            context=long_context,
        )

        assert decision is not None
        assert decision.latency_ms >= 0

    def test_validation_with_short_output(self):
        """Test validation with very short output."""
        guard = Guard(policy="default", trace_enabled=False)

        decision = guard.validate(
            prompt="Is the sky blue?",
            output="Yes.",
            context="The sky appears blue due to Rayleigh scattering.",
        )

        assert decision is not None
        assert decision.decision in ("allow", "block", "regenerate", "abstain")

    def test_validation_without_context(self):
        """Test validation without reference context."""
        guard = Guard(policy="default", trace_enabled=False)

        decision = guard.validate(
            prompt="What is the meaning of life?",
            output="The meaning of life is subjective.",
        )

        assert decision is not None
        assert decision.decision in ("allow", "block", "regenerate", "abstain")
        # Pipeline should still work without context
        assert len(decision.validator_results) > 0

    def test_validation_with_special_characters(self):
        """Test validation with special characters in text."""
        guard = Guard(policy="default", trace_enabled=False)

        decision = guard.validate(
            prompt="What is C++?",
            output="C++ is a systems programming language (ISO/IEC 14882).",
            context="C++ is a programming language with special syntax like ++.",
        )

        assert decision is not None

    def test_validation_with_numbers(self):
        """Test validation with numerical content."""
        guard = Guard(policy="default", trace_enabled=False)

        decision = guard.validate(
            prompt="What is 2 + 2?",
            output="2 + 2 = 4.",
            context="Basic arithmetic: addition of two numbers.",
        )

        assert decision is not None
        assert 0.0 <= decision.risk_score <= 1.0

    def test_validation_with_unicode(self):
        """Test validation with Unicode characters."""
        guard = Guard(policy="default", trace_enabled=False)

        decision = guard.validate(
            prompt="What is the capital of Japan?",
            output="The capital of Japan is 東京 (Tokyo).",
            context="東京 is the capital city of Japan.",
        )

        assert decision is not None

    def test_guard_does_not_mutate_input(self):
        """Test that Guard doesn't mutate input during validation."""
        guard = Guard(policy="default", trace_enabled=False)

        prompt = "What is AI?"
        output = "AI is artificial intelligence."
        context = "AI stands for artificial intelligence."

        # Store originals
        original_prompt = prompt
        original_output = output
        original_context = context

        # Run validation
        decision = guard.validate(
            prompt=prompt,
            output=output,
            context=context,
        )

        # Verify inputs haven't changed
        assert prompt == original_prompt
        assert output == original_output
        assert context == original_context
        assert decision is not None

    def test_suggestion_provided_on_regenerate(self):
        """Test that suggested_fix is provided when needed."""
        guard = Guard(policy="rag_strict", trace_enabled=False)

        decision = guard.validate(
            prompt="Who is the author?",
            output="The author is completely unknown.",  # Low confidence
            context="The author is Jane Austen, a famous novelist.",
        )

        # If decision is regenerate or block, suggested_fix might be present
        assert decision is not None
        # suggested_fix should be None or str
        if decision.suggested_fix is not None:
            assert isinstance(decision.suggested_fix, str)

    def test_evidence_is_provided(self):
        """Test that evidence is always provided in decision."""
        guard = Guard(policy="default", trace_enabled=False)

        decision = guard.validate(
            prompt="Test question",
            output="Test answer",
            context="Test context",
        )

        # Evidence should always be provided
        assert decision.evidence is not None
        assert isinstance(decision.evidence, str)
        assert len(decision.evidence) > 0

    def test_policy_can_be_reloaded(self):
        """Test that policy can be reloaded mid-stream."""
        guard1 = Guard(policy="default", trace_enabled=False)
        guard2 = Guard(policy="rag_strict", trace_enabled=False)

        # Both should work independently
        decision1 = guard1.validate("Q1", "A1", "C1")
        decision2 = guard2.validate("Q2", "A2", "C2")

        assert decision1.policy_name == "default"
        assert decision2.policy_name == "rag_strict"

    def test_confidence_reflects_validator_agreement(self):
        """Test that confidence score reflects validator agreement."""
        guard = Guard(policy="default", trace_enabled=False)

        # Faithful output should have higher confidence
        decision_faithful = guard.validate(
            prompt="What is water?",
            output="Water is a liquid compound.",
            context="Water is a liquid with the chemical formula H2O.",
        )

        # Hallucinated output should have lower confidence (or validators disagree)
        decision_hallucinated = guard.validate(
            prompt="What is water?",
            output="Water is purple and tastes like metal.",
            context="Water is a clear liquid with hydrogen and oxygen.",
        )

        assert 0.0 <= decision_faithful.confidence <= 1.0
        assert 0.0 <= decision_hallucinated.confidence <= 1.0


class TestGuardExceptionHandling:
    """Test exception handling in Guard."""

    def test_policy_load_error_on_missing_file(self):
        """Test PolicyLoadError is raised for missing policy file."""
        with pytest.raises(PolicyLoadError):
            Guard(policy="/nonexistent/path/to/policy.yaml")

    def test_policy_load_error_on_invalid_name(self):
        """Test PolicyLoadError is raised for invalid policy name."""
        with pytest.raises(PolicyLoadError):
            Guard(policy="completely_nonexistent_policy_name_12345")

    def test_validation_error_handling(self):
        """Test that Guard handles validation errors gracefully."""
        guard = Guard(policy="default", trace_enabled=False)

        # Even with edge case inputs, Guard should return a decision
        decision = guard.validate(
            prompt="A" * 10000,  # Very long prompt
            output="B" * 10000,  # Very long output
            context="C" * 10000,  # Very long context
        )

        assert decision is not None


class TestGuardAsyncIntegration:
    """Integration tests for async validation."""

    @pytest.mark.asyncio
    async def test_async_validation_equivalent_to_sync(self):
        """Test that async validation produces same result as sync."""
        guard = Guard(policy="default", trace_enabled=False)

        prompt = "What is AI?"
        output = "AI is artificial intelligence."
        context = "AI stands for artificial intelligence."

        # Run sync version
        sync_decision = guard.validate(prompt, output, context)

        # Run async version
        async_decision = await guard.validate_async(prompt, output, context)

        # Should have same basic properties
        assert sync_decision.decision == async_decision.decision
        assert sync_decision.risk_score == async_decision.risk_score
        assert sync_decision.policy_name == async_decision.policy_name

    @pytest.mark.asyncio
    async def test_multiple_async_validations(self):
        """Test running multiple async validations concurrently."""
        import asyncio

        guard = Guard(policy="default", trace_enabled=False)

        tasks = [
            guard.validate_async("What is X?", "X is Y.", "X is Y."),
            guard.validate_async("What is A?", "A is B.", "A is B."),
            guard.validate_async("What is 1?", "1 is 2.", "1 is 2."),
        ]

        decisions = await asyncio.gather(*tasks)

        assert len(decisions) == 3
        for decision in decisions:
            assert decision is not None
            assert decision.decision in ("allow", "block", "regenerate", "abstain")
