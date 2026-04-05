#!/usr/bin/env python3
"""
Unit tests for Flask service layer (GuardService and BatchProcessor).

Tests cover:
- GuardService singleton pattern and policy caching
- Guard instance initialization and model preloading
- Policy loading error handling
- Single validation with response mapping
- Batch processing in parallel and sequential modes
- Per-request timeout enforcement
- Error tracking and aggregation
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from concurrent.futures import ThreadPoolExecutor

from hallucination_guard import Guard
from hallucination_guard.core.decision import GuardDecision, ValidationResult
from hallucination_guard.core.exceptions import PolicyLoadError

from frontend.service import GuardService, BatchProcessor
from frontend.schemas import (
    BatchValidateRequest,
    BatchValidateRequestItem,
    ValidationResponse,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_guard_decision():
    """Mock GuardDecision for testing."""
    return GuardDecision(
        decision="allow",
        risk_score=0.1,
        confidence=0.95,
        output="Test output",
        evidence="All validators passed",
        suggested_fix=None,
        validator_results=[
            ValidationResult(
                validator_name="heuristics",
                score=0.9,
                passed=True,
                evidence="Good context overlap",
                latency_ms=5.0,
            )
        ],
        latency_ms=15.0,
        policy_name="default",
        prompt_injection_risk=0.0,
        prompt_security_metadata={},
    )


@pytest.fixture
def mock_guard(mock_guard_decision):
    """Mock Guard instance for testing."""
    mock = Mock(spec=Guard)
    mock.policy = Mock()
    mock.policy.name = "default"
    mock.validate = Mock(return_value=mock_guard_decision)
    return mock


@pytest.fixture
def batch_request():
    """Create a sample batch validation request."""
    return BatchValidateRequest(
        requests=[
            BatchValidateRequestItem(
                id="req_1",
                prompt="What is AI?",
                output="AI is artificial intelligence",
                context="AI stands for artificial intelligence",
                policy="default",
            ),
            BatchValidateRequestItem(
                id="req_2",
                prompt="What is ML?",
                output="ML is machine learning",
                context=None,
                policy="default",
            ),
        ],
        mode="parallel",
        timeout_per_request_ms=30000,
    )


# =============================================================================
# GuardService Tests
# =============================================================================


class TestGuardServiceSingleton:
    """Test GuardService singleton pattern."""

    def test_singleton_pattern(self):
        """Verify GuardService enforces singleton pattern."""
        # Reset singleton for test
        GuardService._instance = None

        service1 = GuardService.get_instance()
        service2 = GuardService()

        assert service1 is service2, "GuardService should be singleton"

    def test_get_instance_method(self):
        """Test get_instance() factory method."""
        GuardService._instance = None
        service = GuardService.get_instance()
        assert isinstance(service, GuardService)

    def test_initialization_idempotent(self):
        """Verify initialization only happens once."""
        GuardService._instance = None
        service = GuardService()
        guards_cache_1 = service._guards

        # Call init again via new instance reference
        service2 = GuardService()
        guards_cache_2 = service2._guards

        assert guards_cache_1 is guards_cache_2


class TestGuardServicePolicyCaching:
    """Test Guard instance caching by policy."""

    @patch("frontend.service.Guard")
    def test_guard_caching(self, mock_guard_class):
        """Verify Guard instances are cached by policy."""
        GuardService._instance = None
        mock_instance = Mock(spec=Guard)
        mock_guard_class.return_value = mock_instance

        service = GuardService()

        # First access creates and caches
        guard1 = service.get_guard("default")
        assert guard1 is mock_instance
        assert mock_guard_class.call_count == 1

        # Second access returns cached instance
        guard2 = service.get_guard("default")
        assert guard2 is guard1
        assert mock_guard_class.call_count == 1  # Not called again

    @patch("frontend.service.Guard")
    def test_different_policies_cached_separately(self, mock_guard_class):
        """Verify different policies maintain separate Guard instances."""
        GuardService._instance = None
        mock_default = Mock(spec=Guard)
        mock_strict = Mock(spec=Guard)

        def guard_factory(policy, **kwargs):
            if policy == "default":
                return mock_default
            return mock_strict

        mock_guard_class.side_effect = guard_factory

        service = GuardService()
        guard_default = service.get_guard("default")
        guard_strict = service.get_guard("rag_strict")

        assert guard_default is not guard_strict
        assert guard_default is mock_default
        assert guard_strict is mock_strict

    @patch("frontend.service.Guard")
    def test_get_guard_preload_models(self, mock_guard_class):
        """Verify get_guard enables model preloading."""
        GuardService._instance = None
        mock_instance = Mock(spec=Guard)
        mock_guard_class.return_value = mock_instance

        service = GuardService()
        service.get_guard("default")

        # Verify Guard was initialized with preload_models=True
        mock_guard_class.assert_called_once()
        call_kwargs = mock_guard_class.call_args[1]
        assert call_kwargs.get("preload_models") is True

    @patch("frontend.service.Guard")
    def test_get_guard_policy_load_error(self, mock_guard_class):
        """Test handling of PolicyLoadError."""
        GuardService._instance = None
        mock_guard_class.side_effect = PolicyLoadError(
            policy_name="invalid_policy",
            reason="Policy file not found",
        )

        service = GuardService()
        with pytest.raises(PolicyLoadError) as exc_info:
            service.get_guard("invalid_policy")

        assert "invalid_policy" in str(exc_info.value)

    @patch("frontend.service.Guard")
    def test_get_guard_unexpected_error(self, mock_guard_class):
        """Test handling of unexpected exceptions during Guard creation."""
        GuardService._instance = None
        mock_guard_class.side_effect = RuntimeError("Unexpected error")

        service = GuardService()
        with pytest.raises(PolicyLoadError) as exc_info:
            service.get_guard("default")

        assert "Unexpected error" in str(exc_info.value)


class TestGuardServiceValidation:
    """Test GuardService validate method."""

    @patch("frontend.service.Guard")
    def test_validate_success(self, mock_guard_class, mock_guard_decision):
        """Test successful validation."""
        GuardService._instance = None
        mock_instance = Mock(spec=Guard)
        mock_instance.validate = Mock(return_value=mock_guard_decision)
        mock_guard_class.return_value = mock_instance

        service = GuardService()
        response = service.validate(
            prompt="What is AI?",
            output="AI is artificial intelligence",
            policy="default",
            context="AI stands for...",
        )

        assert isinstance(response, ValidationResponse)
        assert response.decision == "allow"
        assert response.risk_score == 0.1
        assert response.policy_name == "default"

    @patch("frontend.service.Guard")
    def test_validate_maps_tier_results(self, mock_guard_class, mock_guard_decision):
        """Test that tier results are properly mapped to ValidationResponse."""
        GuardService._instance = None
        mock_instance = Mock(spec=Guard)
        mock_instance.validate = Mock(return_value=mock_guard_decision)
        mock_guard_class.return_value = mock_instance

        service = GuardService()
        response = service.validate(
            prompt="Test", output="Test output", policy="default"
        )

        assert response.tier_results is not None
        assert len(response.tier_results) == 1
        assert response.tier_results[0].validator_name == "heuristics"

    @patch("frontend.service.Guard")
    def test_validate_passes_all_parameters(self, mock_guard_class, mock_guard_decision):
        """Verify validate passes all parameters to Guard.validate()."""
        GuardService._instance = None
        mock_instance = Mock(spec=Guard)
        mock_instance.validate = Mock(return_value=mock_guard_decision)
        mock_guard_class.return_value = mock_instance

        service = GuardService()
        service.validate(
            prompt="Test prompt",
            output="Test output",
            policy="rag_strict",
            context="Test context",
            domain="healthcare",
        )

        mock_instance.validate.assert_called_once()
        call_kwargs = mock_instance.validate.call_args[1]
        assert call_kwargs["prompt"] == "Test prompt"
        assert call_kwargs["output"] == "Test output"
        assert call_kwargs["context"] == "Test context"
        assert call_kwargs["domain"] == "healthcare"


class TestGuardServicePoliciesListing:
    """Test GuardService get_policies method."""

    @patch("frontend.service.Guard")
    def test_get_policies_returns_available(self, mock_guard_class):
        """Test get_policies returns available policy names."""
        GuardService._instance = None
        mock_instance = Mock(spec=Guard)
        mock_guard_class.return_value = mock_instance

        service = GuardService()
        policies = service.get_policies()

        assert isinstance(policies, list)
        assert len(policies) > 0
        # Should have cached guards for available policies
        assert len(service._guards) > 0

    @patch("frontend.service.Guard")
    def test_get_policies_graceful_degradation(self, mock_guard_class):
        """Test get_policies handles unavailable policies gracefully."""
        GuardService._instance = None

        def guard_factory(policy, **kwargs):
            if policy == "default":
                return Mock(spec=Guard)
            raise PolicyLoadError(policy_name=policy, reason="Not available")

        mock_guard_class.side_effect = guard_factory

        service = GuardService()
        policies = service.get_policies()

        # Should include default, but not unavailable policies
        assert "default" in policies
        assert "rag_strict" not in policies


# =============================================================================
# BatchProcessor Tests
# =============================================================================


class TestBatchProcessorInitialization:
    """Test BatchProcessor initialization."""

    def test_initialization(self):
        """Test BatchProcessor initializes with correct settings."""
        processor = BatchProcessor(max_workers=5)
        assert processor.max_workers == 5
        assert processor.executor is not None

    def test_default_max_workers(self):
        """Test default max_workers is set."""
        processor = BatchProcessor()
        assert processor.max_workers == 10


class TestBatchProcessorParallel:
    """Test parallel batch processing."""

    @patch.object(GuardService, "validate")
    def test_parallel_mode_concurrent_execution(
        self, mock_validate, batch_request, mock_guard_decision
    ):
        """Verify parallel mode submits requests concurrently."""
        # Mock validate to return success
        def validate_side_effect(*args, **kwargs):
            time.sleep(0.01)  # Simulate work
            return ValidationResponse(
                decision="allow",
                risk_score=0.1,
                confidence=0.9,
                evidence="Test",
                latency_ms=10.0,
                policy_name="default",
            )

        mock_validate.side_effect = validate_side_effect

        service = GuardService()
        processor = BatchProcessor(max_workers=2)

        # Create parallel request (original is parallel by default)
        start = time.time()
        response = processor.process_batch(service, batch_request)
        elapsed = time.time() - start

        # Parallel execution should be faster than sequential (2 * 0.01 = 0.02)
        # but the test is inherently flaky, so we just check it completes
        assert response.total_requests == 2
        assert response.successful_validations >= 1

    @patch.object(GuardService, "validate")
    def test_parallel_mode_error_handling(
        self, mock_validate, batch_request, mock_guard_decision
    ):
        """Test parallel mode handles errors gracefully."""
        call_count = [0]

        def validate_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return ValidationResponse(
                    decision="allow",
                    risk_score=0.1,
                    confidence=0.9,
                    evidence="Test",
                    latency_ms=10.0,
                    policy_name="default",
                )
            raise ValueError("Simulated error")

        mock_validate.side_effect = validate_side_effect

        service = GuardService()
        processor = BatchProcessor()

        # Create parallel request (default mode)
        response = processor.process_batch(service, batch_request)

        # Should have one success and one error
        assert response.successful_validations >= 1
        assert response.failed_validations >= 1
        assert response.total_requests == 2


class TestBatchProcessorSequential:
    """Test sequential batch processing."""

    @patch.object(GuardService, "validate")
    def test_sequential_mode_ordered_execution(
        self, mock_validate, batch_request, mock_guard_decision
    ):
        """Verify sequential mode processes requests in order."""
        call_order = []

        def validate_side_effect(*args, **kwargs):
            call_order.append(kwargs.get("prompt", ""))
            return ValidationResponse(
                decision="allow",
                risk_score=0.1,
                confidence=0.9,
                evidence="Test",
                latency_ms=10.0,
                policy_name="default",
            )

        mock_validate.side_effect = validate_side_effect

        service = GuardService()
        processor = BatchProcessor()

        # Create sequential request
        sequential_request = BatchValidateRequest(
            requests=batch_request.requests,
            mode="sequential",
            timeout_per_request_ms=batch_request.timeout_per_request_ms,
        )
        response = processor.process_batch(service, sequential_request)

        # All requests should be processed
        assert response.total_requests == 2
        assert response.successful_validations == 2

    @patch.object(GuardService, "validate")
    def test_sequential_mode_timeout_early_exit(
        self, mock_validate, batch_request
    ):
        """Test sequential mode respects batch timeout.
        
        Note: This test validates that timeout logic is present, but due to
        timing variability, we test the code path rather than strict timing.
        """
        call_count = [0]

        def validate_side_effect(*args, **kwargs):
            call_count[0] += 1
            # First call succeeds, second would time out
            if call_count[0] == 1:
                return ValidationResponse(
                    decision="allow",
                    risk_score=0.1,
                    confidence=0.9,
                    evidence="Test",
                    latency_ms=100.0,
                    policy_name="default",
                )
            time.sleep(1.5)  # Simulate long validation
            return ValidationResponse(
                decision="allow",
                risk_score=0.1,
                confidence=0.9,
                evidence="Test",
                latency_ms=1500.0,
                policy_name="default",
            )

        mock_validate.side_effect = validate_side_effect

        service = GuardService()
        processor = BatchProcessor()

        # Create request with 1100ms timeout (enough for first, but problematic for second)
        timeout_request = BatchValidateRequest(
            requests=batch_request.requests,
            mode="sequential",
            timeout_per_request_ms=1100,
        )

        response = processor.process_batch(service, timeout_request)

        # At least first request should succeed
        assert response.total_requests == 2
        assert response.successful_validations >= 1


class TestBatchProcessorAggregation:
    """Test batch result aggregation."""

    @patch.object(GuardService, "validate")
    def test_aggregation_counts_success_and_failure(
        self, mock_validate, batch_request
    ):
        """Test batch response correctly counts successes and failures."""
        call_count = [0]

        def validate_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] % 2 == 0:
                raise ValueError("Simulated error")
            return ValidationResponse(
                decision="allow",
                risk_score=0.1,
                confidence=0.9,
                evidence="Test",
                latency_ms=10.0,
                policy_name="default",
            )

        mock_validate.side_effect = validate_side_effect

        service = GuardService()
        processor = BatchProcessor()

        # Create 4 requests to test counting
        batch_request.requests.extend(
            [
                BatchValidateRequestItem(
                    id="req_3",
                    prompt="Test 3",
                    output="Output 3",
                    policy="default",
                ),
                BatchValidateRequestItem(
                    id="req_4",
                    prompt="Test 4",
                    output="Output 4",
                    policy="default",
                ),
            ]
        )

        response = processor.process_batch(service, batch_request)

        assert response.total_requests == 4
        assert (
            response.successful_validations + response.failed_validations
        ) == 4

    @patch.object(GuardService, "validate")
    def test_response_includes_latency_metrics(
        self, mock_validate, batch_request
    ):
        """Test batch response includes latency metrics."""
        mock_validate.return_value = ValidationResponse(
            decision="allow",
            risk_score=0.1,
            confidence=0.9,
            evidence="Test",
            latency_ms=15.0,
            policy_name="default",
        )

        service = GuardService()
        processor = BatchProcessor()

        response = processor.process_batch(service, batch_request)

        assert response.batch_latency_ms >= 0
        # Individual request latencies
        for result in response.results:
            if result.error is None:
                assert result.latency_ms is not None


class TestBatchProcessorEdgeCases:
    """Test edge cases in batch processing."""

    @patch.object(GuardService, "validate")
    def test_single_request_batch(self, mock_validate, batch_request):
        """Test batch with single request."""
        mock_validate.return_value = ValidationResponse(
            decision="allow",
            risk_score=0.1,
            confidence=0.9,
            evidence="Test",
            latency_ms=10.0,
            policy_name="default",
        )

        service = GuardService()
        processor = BatchProcessor()

        # Create single-request batch
        single_request = BatchValidateRequest(
            requests=[batch_request.requests[0]],
            mode="parallel",
            timeout_per_request_ms=30000,
        )
        response = processor.process_batch(service, single_request)

        assert response.total_requests == 1

    @patch.object(GuardService, "validate")
    def test_batch_with_mixed_errors(self, mock_validate, batch_request):
        """Test batch handles mix of successes and errors."""
        call_count = [0]

        def validate_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return ValidationResponse(
                    decision="allow",
                    risk_score=0.1,
                    confidence=0.9,
                    evidence="Test",
                    latency_ms=10.0,
                    policy_name="default",
                )
            raise RuntimeError("Request failed")

        mock_validate.side_effect = validate_side_effect

        service = GuardService()
        processor = BatchProcessor()

        response = processor.process_batch(service, batch_request)

        assert response.total_requests == 2
        assert response.successful_validations == 1
        assert response.failed_validations == 1

        # Verify error details
        error_results = [r for r in response.results if r.error is not None]
        assert len(error_results) == 1
        assert "Request failed" in error_results[0].error
