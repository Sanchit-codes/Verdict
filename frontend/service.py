#!/usr/bin/env python3
"""
Flask service layer for HallucinationGuard validation.

Provides:
- GuardService: Singleton pattern for Guard instances, policy caching, model pre-warming
- BatchProcessor: Parallel/sequential batch validation with timeout handling

These services abstract the Guard SDK and handle caching, concurrency, and graceful
error handling for the REST API routes.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import List, Optional

from hallucination_guard import Guard
from hallucination_guard.core.decision import GuardDecision
from hallucination_guard.core.exceptions import PolicyLoadError

from frontend.schemas import (
    ValidationResponse,
    BatchValidateRequest,
    BatchValidateRequestItem,
    BatchValidationResponse,
    BatchValidationResultItem,
    ValidationTierResult,
)

logger = logging.getLogger(__name__)


# =============================================================================
# GuardService: Singleton Guard wrapper with policy caching
# =============================================================================


class GuardService:
    """
    Singleton service for Guard instance management.

    Maintains a cache of Guard instances keyed by policy name to avoid
    re-loading policies and models. Pre-warms models on initialization
    for production-like latency.

    Attributes:
        _instance: Singleton instance (class-level).
        _guards: Dict of Guard instances by policy name.
        _lock: Thread-safe lock for singleton and cache access.
    """

    _instance: Optional["GuardService"] = None
    _lock: Lock = Lock()

    def __new__(cls) -> "GuardService":
        """Enforce singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize GuardService singleton (once only)."""
        if self._initialized:
            return

        self._guards: dict[str, Guard] = {}
        self._lock_guards: Lock = Lock()
        self._initialized = True
        logger.info("GuardService initialized")

    @staticmethod
    def get_instance() -> "GuardService":
        """Get or create the singleton instance."""
        return GuardService()

    def get_guard(self, policy: str) -> Guard:
        """
        Get or create a Guard instance for the given policy.

        Guard instances are cached by policy name. On first access, the Guard
        is created with model preloading enabled (preload_models=True) to
        reduce first-request latency. Subsequent requests reuse the cached
        instance.

        Args:
            policy: Policy name (e.g., "default", "rag_strict", "chatbot").

        Returns:
            Guard instance configured with the requested policy.

        Raises:
            PolicyLoadError: If the policy cannot be loaded or is invalid.
        """
        # Fast path: return cached Guard if available
        if policy in self._guards:
            return self._guards[policy]

        # Slow path: load policy and create Guard (thread-safe)
        with self._lock_guards:
            # Double-check after acquiring lock
            if policy in self._guards:
                return self._guards[policy]

            logger.info(f"Loading Guard for policy '{policy}'")
            try:
                guard = Guard(policy=policy, preload_models=True)
                self._guards[policy] = guard
                logger.info(f"Guard for policy '{policy}' loaded and cached")
                return guard
            except PolicyLoadError as e:
                logger.error(f"Failed to load policy '{policy}': {e.reason}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error loading policy '{policy}': {e}")
                raise PolicyLoadError(
                    policy_name=policy,
                    reason=str(e),
                ) from e

    def get_policies(self) -> List[str]:
        """
        Get list of available policy names.

        This method loads policy metadata by attempting to instantiate Guards
        for known policy names. Unavailable policies are logged but do not
        raise exceptions (graceful degradation).

        Returns:
            List of available policy names (e.g., ["default", "rag_strict"]).
        """
        known_policies = ["default", "rag_strict", "chatbot"]
        available = []

        for policy_name in known_policies:
            try:
                self.get_guard(policy_name)
                available.append(policy_name)
            except Exception as e:
                logger.warning(f"Policy '{policy_name}' not available: {e}")

        return available

    @staticmethod
    def _guard_decision_to_response(
        decision: GuardDecision, policy_name: str, output: str
    ) -> ValidationResponse:
        """
        Convert GuardDecision to ValidationResponse.

        Maps SDK GuardDecision to the REST API schema, including tier results
        and optional metadata.

        Args:
            decision: GuardDecision from Guard.validate().
            policy_name: Policy name used for validation.
            output: Original output text (for reference).

        Returns:
            ValidationResponse matching REST schema.
        """
        # Convert validator results to tier results
        tier_results = None
        if decision.validator_results:
            tier_results = [
                ValidationTierResult(
                    validator_name=vr.validator_name,
                    score=vr.score,
                    passed=vr.passed,
                    evidence=vr.evidence,
                    latency_ms=vr.latency_ms,
                )
                for vr in decision.validator_results
            ]

        return ValidationResponse(
            decision=decision.decision,
            risk_score=decision.risk_score,
            confidence=decision.confidence,
            evidence=decision.evidence,
            output=output,
            suggested_fix=decision.suggested_fix,
            latency_ms=decision.latency_ms,
            policy_name=policy_name,
            tier_results=tier_results,
        )

    def validate(
        self,
        prompt: str,
        output: str,
        policy: str,
        context: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> ValidationResponse:
        """
        Validate output using the specified policy.

        Wraps Guard.validate() and maps the GuardDecision to ValidationResponse.
        Gracefully handles errors by returning a response with error details.

        Args:
            prompt: User prompt or query.
            output: LLM-generated output to validate.
            policy: Policy name (e.g., "default").
            context: Optional reference context.
            domain: Optional domain metadata.

        Returns:
            ValidationResponse with decision and evidence.
        """
        try:
            guard = self.get_guard(policy)
            decision = guard.validate(
                prompt=prompt,
                output=output,
                context=context,
                domain=domain,
            )
            return self._guard_decision_to_response(decision, policy, output)
        except PolicyLoadError as e:
            logger.error(f"Policy load error: {e}")
            raise
        except Exception as e:
            logger.error(f"Validation error: {e}", exc_info=True)
            raise


# =============================================================================
# BatchProcessor: Parallel/sequential batch validation
# =============================================================================


class BatchProcessor:
    """
    Batch validation processor with parallel and sequential modes.

    Handles concurrent validation of multiple requests using ThreadPoolExecutor,
    with per-request timeout enforcement and error tracking.

    Attributes:
        max_workers: Maximum concurrent threads (default: 10).
    """

    def __init__(self, max_workers: int = 10):
        """
        Initialize BatchProcessor.

        Args:
            max_workers: Maximum number of concurrent worker threads (default: 10).
        """
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        logger.info(f"BatchProcessor initialized with max_workers={max_workers}")

    def process_batch(
        self,
        guard_service: GuardService,
        request: BatchValidateRequest,
    ) -> BatchValidationResponse:
        """
        Process a batch of validation requests.

        Dispatches to parallel or sequential processing based on request mode.
        Returns aggregated results with per-request latency and error tracking.

        Args:
            guard_service: GuardService instance for validation.
            request: BatchValidateRequest with mode, requests, and timeout_ms.

        Returns:
            BatchValidationResponse with results and aggregated metrics.
        """
        batch_start = time.time()

        if request.mode == "parallel":
            results = self._process_parallel(guard_service, request)
        else:  # sequential
            results = self._process_sequential(guard_service, request)

        batch_latency = (time.time() - batch_start) * 1000  # ms

        # Count successes and failures
        successful = sum(1 for r in results if r.decision is not None)
        failed = len(results) - successful

        return BatchValidationResponse(
            batch_id="",  # Optional batch_id tracking
            total_requests=len(results),
            successful_validations=successful,
            failed_validations=failed,
            results=results,
            batch_latency_ms=batch_latency,
            errors=None,
        )

    def _process_parallel(
        self,
        guard_service: GuardService,
        request: BatchValidateRequest,
    ) -> List[BatchValidationResultItem]:
        """
        Process requests in parallel mode.

        Submits all requests to ThreadPoolExecutor and collects results with
        per-request timeout enforcement.

        Args:
            guard_service: GuardService instance.
            request: BatchValidateRequest.

        Returns:
            List of BatchValidationResultItem with results or errors.
        """
        timeout_per_request = request.timeout_per_request_ms / 1000.0  # Convert to seconds

        # Submit all requests to thread pool
        futures = {}
        for req_item in request.requests:
            future = self.executor.submit(
                self._validate_single,
                guard_service,
                req_item,
            )
            futures[future] = req_item.id

        # Collect results with timeout
        results = []
        for future in as_completed(futures, timeout=timeout_per_request):
            req_id = futures[future]
            try:
                result = future.result(timeout=timeout_per_request)
                results.append(result)
            except TimeoutError:
                logger.warning(f"Request {req_id} timed out")
                results.append(
                    BatchValidationResultItem(
                        id=req_id,
                        error=f"Request timed out after {timeout_per_request*1000:.0f}ms",
                    )
                )
            except Exception as e:
                logger.error(f"Request {req_id} failed: {e}")
                results.append(
                    BatchValidationResultItem(
                        id=req_id,
                        error=str(e),
                    )
                )

        return results

    def _process_sequential(
        self,
        guard_service: GuardService,
        request: BatchValidateRequest,
    ) -> List[BatchValidationResultItem]:
        """
        Process requests sequentially in order.

        Validates requests one at a time, respecting overall batch timeout.
        Stops early if batch timeout exceeded (graceful degradation).

        Args:
            guard_service: GuardService instance.
            request: BatchValidateRequest.

        Returns:
            List of BatchValidationResultItem with results or errors.
        """
        batch_start = time.time()
        timeout_per_request = request.timeout_per_request_ms / 1000.0  # seconds

        results = []
        for req_item in request.requests:
            elapsed = time.time() - batch_start
            if elapsed > timeout_per_request:
                logger.warning(
                    f"Batch timeout exceeded; skipping request {req_item.id}"
                )
                results.append(
                    BatchValidationResultItem(
                        id=req_item.id,
                        error="Batch timeout exceeded",
                    )
                )
                continue

            try:
                result = self._validate_single(guard_service, req_item)
                results.append(result)
            except Exception as e:
                logger.error(f"Request {req_item.id} failed: {e}")
                results.append(
                    BatchValidationResultItem(
                        id=req_item.id,
                        error=str(e),
                    )
                )

        return results

    @staticmethod
    def _validate_single(
        guard_service: GuardService,
        req_item: BatchValidateRequestItem,
    ) -> BatchValidationResultItem:
        """
        Validate a single request item.

        Args:
            guard_service: GuardService instance.
            req_item: BatchValidateRequestItem.

        Returns:
            BatchValidationResultItem with result or error.
        """
        req_start = time.time()
        try:
            response = guard_service.validate(
                prompt=req_item.prompt,
                output=req_item.output,
                policy=req_item.policy,
                context=req_item.context,
                domain=req_item.domain,
            )
            req_latency = (time.time() - req_start) * 1000  # ms

            return BatchValidationResultItem(
                id=req_item.id,
                decision=response.decision,
                risk_score=response.risk_score,
                confidence=response.confidence,
                evidence=response.evidence,
                latency_ms=req_latency,
            )
        except Exception as e:
            logger.error(f"Validation error for request {req_item.id}: {e}")
            return BatchValidationResultItem(
                id=req_item.id,
                error=str(e),
            )
