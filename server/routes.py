"""API route handlers for HallucinationGuard Flask backend."""

import logging
import sys
import threading
import time
from datetime import datetime
from typing import Any

from flask import Blueprint, jsonify, request

from hallucination_guard import Guard
from hallucination_guard.core.exceptions import IntentViolationError

from .config import Config
from .gemini_generator import GeminiGenerator
from .middleware import log_request
from .schemas import (
    ActionEnforcementInfo,
    BatchValidateRequest,
    BatchValidateResponse,
    ErrorResponse,
    GenerateRequest,
    GenerateResponse,
    GenerationLatency,
    HealthResponse,
    ValidateRequest,
    ValidationDecision,
    ValidationTierResult,
    VersionResponse,
)

logger = logging.getLogger(__name__)

# Global state for model warmup
_warmup_complete = threading.Event()
_guard_instance: Guard | None = None
_generator_instance: GeminiGenerator | None = None


def init_guard(config: Config) -> None:
    """Initialize the Guard instance and preload models."""
    global _guard_instance

    logger.info(f"Initializing Guard with policy={config.DEFAULT_POLICY}")

    try:
        _guard_instance = Guard(
            policy=config.DEFAULT_POLICY,
            trace_enabled=config.ENABLE_TRACE_EXPORT,
        )
        logger.info("Guard initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize Guard: {e}", exc_info=True)
        _guard_instance = None


def preload_models(config: Config) -> None:
    """Preload ML models in background to avoid cold-start latency."""
    if not config.PRELOAD_MODELS:
        _warmup_complete.set()
        return

    def _do_warmup() -> None:
        try:
            logger.info("[Warmup] Starting model preload in background...")
            # Initialize Guard which will load models on first use
            init_guard(config)
            logger.info("[Warmup] Model preload complete")
        except Exception as e:
            logger.error(f"[Warmup] Model preload failed: {e}", exc_info=True)
        finally:
            _warmup_complete.set()

    thread = threading.Thread(target=_do_warmup, daemon=True, name="model-warmup")
    thread.start()


def wait_for_warmup(timeout_secs: float = 60.0) -> bool:
    """Wait for model warmup to complete."""
    return _warmup_complete.wait(timeout=timeout_secs)


def get_guard(policy: str = "default") -> Guard | None:
    """Get Guard instance, initializing if needed."""
    global _guard_instance

    if _guard_instance is None:
        logger.warning("Guard not initialized, initializing now...")
        config = Config()
        init_guard(config)

    # If policy differs from current, create a new instance
    if _guard_instance and policy != _guard_instance.policy.name:
        logger.info(f"Switching policy from {_guard_instance.policy.name} to {policy}")
        _guard_instance = Guard(policy=policy)

    return _guard_instance


def get_generator(model: str | None = None) -> GeminiGenerator | None:
    """Get or create GeminiGenerator instance.

    Args:
        model: Gemini model to use. If None, uses default from config.

    Returns:
        GeminiGenerator instance or None if Gemini API is not available.
    """
    global _generator_instance

    # Return existing instance if API key is still configured
    if _generator_instance is not None:
        return _generator_instance

    # Try to create new instance
    try:
        _generator_instance = GeminiGenerator(model=model or "gemini-2.5-flash")
        logger.info(f"GeminiGenerator initialized: {model or 'default'}")
        return _generator_instance
    except (ImportError, ValueError) as e:
        logger.warning(f"GeminiGenerator not available: {e}")
        return None


def create_routes(app: Any, config: Config) -> Blueprint:
    """Create and register API routes."""
    bp = Blueprint("api", __name__, url_prefix="/api")

    @bp.route("/health", methods=["GET"])
    @log_request
    def health() -> tuple:
        """Health check endpoint.

        Returns:
            HealthResponse with status and model availability.
        """
        try:
            # Try to get Guard instance (creates if needed)
            guard = get_guard()

            # Check model availability
            models_loaded = {
                "heuristics": True,  # Always available
                "embedding": True,  # Check if available
                "hhem": True,  # Check if available
            }

            status = "healthy" if guard is not None else "degraded"

            response = HealthResponse(
                status=status,
                timestamp=datetime.utcnow().isoformat() + "Z",
                models_loaded=models_loaded,
                guard_available=guard is not None,
            )

            return jsonify(response.model_dump()), 200

        except Exception as e:
            logger.error(f"Health check error: {e}", exc_info=True)
            response = HealthResponse(
                status="degraded",
                timestamp=datetime.utcnow().isoformat() + "Z",
                models_loaded={"heuristics": False, "embedding": False, "hhem": False},
                guard_available=False,
            )
            return jsonify(response.model_dump()), 503

    @bp.route("/version", methods=["GET"])
    @log_request
    def version() -> tuple:
        """Version information endpoint.

        Returns:
            VersionResponse with server, SDK, and Python versions.
        """
        try:
            # Get HallucinationGuard version from package metadata
            try:
                from hallucination_guard import __version__

                guard_version = __version__
            except (ImportError, AttributeError):
                guard_version = "unknown"

            response = VersionResponse(
                version=config.SERVER_VERSION,
                guard_version=guard_version,
                python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            )
            return jsonify(response.model_dump()), 200

        except Exception as e:
            logger.error(f"Version endpoint error: {e}", exc_info=True)
            error = ErrorResponse(
                error="Failed to retrieve version information",
                code="SERVER_ERROR",
                details={"message": str(e)},
            )
            return jsonify(error.model_dump()), 500


    @bp.route("/generate", methods=["POST"])
    @log_request
    def generate() -> tuple:
        """Generate text using Gemini and validate with HallucinationGuard.

        Request body:
            GenerateRequest with prompt, context, policy, domain, model, temperature, max_tokens

        Returns:
            GenerateResponse with generated_text, decision, latencies, and tier_results
        """
        overall_start = time.time()

        try:
            # Parse request
            req_data = request.get_json()
            if not req_data:
                error = ErrorResponse(
                    error="Request body must be valid JSON",
                    code="BAD_REQUEST",
                    details={"received": "null"},
                )
                return jsonify(error.model_dump()), 400

            req = GenerateRequest(**req_data)

            # Get generator instance
            generator = get_generator(model=req.model)
            if generator is None:
                error = ErrorResponse(
                    error="Gemini API not available. Set GOOGLE_API_KEY environment variable.",
                    code="SERVICE_UNAVAILABLE",
                    details={"required": "GOOGLE_API_KEY"},
                )
                logger.warning("Generate request received but Gemini not available")
                return jsonify(error.model_dump()), 503

            # Generate text
            gen_start = time.time()
            gen_result = generator.generate(
                prompt=req.prompt,
                context=req.context,
                temperature=req.temperature or 0.7,
                max_tokens=req.max_tokens or 1024,
            )
            gen_latency_ms = (time.time() - gen_start) * 1000

            if gen_result["error"] is not None:
                logger.error(f"Generation failed: {gen_result['error']}")
                error = ErrorResponse(
                    error=f"Text generation failed: {gen_result['error']}",
                    code="GENERATION_ERROR",
                    details={"model": gen_result["model"]},
                )
                return jsonify(error.model_dump()), 500

            generated_text = gen_result["generated_text"]
            if not generated_text:
                error = ErrorResponse(
                    error="Text generation produced empty output",
                    code="GENERATION_ERROR",
                    details={"model": gen_result["model"]},
                )
                return jsonify(error.model_dump()), 422

            logger.debug(
                f"Generated {len(generated_text)} chars in {gen_result['latency_ms']:.1f}ms"
            )

            # Validate generated text
            policy = req.policy or "default"
            guard = get_guard(policy=policy)

            if guard is None:
                error = ErrorResponse(
                    error="HallucinationGuard not available",
                    code="SERVER_ERROR",
                    details={"policy": policy},
                )
                return jsonify(error.model_dump()), 500

            val_start = time.time()
            try:
                decision = guard.validate(
                    prompt=req.prompt,
                    output=generated_text,
                    context=req.context,
                    domain=req.domain or config.DEFAULT_DOMAIN,
                )
            except IntentViolationError as e:
                logger.warning(f"ArmorIQ enforcement in generate: {e.reason}")
                error = ErrorResponse(
                    error=f"Action enforcement failed: {e.reason}",
                    code="ACTION_BLOCKED",
                    details={"reason": e.reason},
                )
                return jsonify(error.model_dump()), 403

            val_latency_ms = (time.time() - val_start) * 1000

            # Build response
            tier_results = None
            if decision.validator_results:
                tier_results = [
                    ValidationTierResult(
                        validator_name=vr.validator_name,
                        score=round(vr.score, 4),
                        passed=vr.passed,
                        evidence=vr.evidence,
                        latency_ms=round(vr.latency_ms, 2),
                        error=vr.error,
                    )
                    for vr in decision.validator_results
                ]

            overall_latency_ms = (time.time() - overall_start) * 1000

            response = GenerateResponse(
                generated_text=generated_text,
                decision=decision.decision,
                risk_score=round(decision.risk_score, 4),
                confidence=round(decision.confidence, 4),
                evidence=decision.evidence,
                latency_ms=GenerationLatency(
                    generation_ms=round(gen_result["latency_ms"], 2),
                    validation_ms=round(decision.latency_ms, 2),
                    total_ms=round(overall_latency_ms, 2),
                ),
                tier_results=tier_results,
                policy_name=decision.policy_name,
                model=req.model or "gemini-2.5-flash",
            )

            logger.info(
                f"Generation complete: decision={response.decision}, "
                f"risk={response.risk_score:.3f}, "
                f"gen_latency={gen_result['latency_ms']:.1f}ms, "
                f"val_latency={decision.latency_ms:.1f}ms, "
                f"total={overall_latency_ms:.1f}ms"
            )

            return jsonify(response.model_dump(exclude_none=True)), 200

        except ValueError as e:
            logger.warning(f"Generate input validation error: {e}")
            error = ErrorResponse(
                error=f"Invalid request: {str(e)}",
                code="VALIDATION_ERROR",
                details={"message": str(e)},
            )
            return jsonify(error.model_dump()), 422

        except Exception as e:
            logger.error(f"Generate endpoint error: {e}", exc_info=True)
            error = ErrorResponse(
                error="Text generation pipeline failed",
                code="SERVER_ERROR",
                details={"message": str(e)},
            )
            return jsonify(error.model_dump()), 500

    @bp.route("/validate", methods=["POST"])
    @log_request
    def validate() -> tuple:
        """Validate model output against hallucinations.

        Request body:
            ValidateRequest with prompt, output, context, policy, domain, action_plan, user_task

        Returns:
            ValidationDecision with risk_score, decision, evidence, tier_results
        """
        try:
            # Parse request
            req_data = request.get_json()
            if not req_data:
                error = ErrorResponse(
                    error="Request body must be valid JSON",
                    code="BAD_REQUEST",
                    details={"received": "null"},
                )
                return jsonify(error.model_dump()), 400

            req = ValidateRequest(**req_data)

            # Get Guard instance with specified policy
            policy = req.policy or "default"
            guard = get_guard(policy=policy)

            if guard is None:
                error = ErrorResponse(
                    error="HallucinationGuard not available",
                    code="SERVER_ERROR",
                    details={"policy": policy},
                )
                return jsonify(error.model_dump()), 500

            # Run validation
            logger.debug(
                f"Validating: prompt={req.prompt[:50]}..., "
                f"output={req.output[:50]}..., context_len={len(req.context or '')}"
            )

            try:
                decision = guard.validate(
                    prompt=req.prompt,
                    output=req.output,
                    context=req.context,
                    domain=req.domain or config.DEFAULT_DOMAIN,
                    action_plan=req.action_plan,
                    user_task=req.user_task,
                )
            except IntentViolationError as e:
                # ArmorIQ blocked the action
                logger.warning(f"ArmorIQ enforcement: action blocked - {e.reason}")
                error = ErrorResponse(
                    error=f"Action enforcement failed: {e.reason}",
                    code="ACTION_BLOCKED",
                    details={"reason": e.reason},
                )
                return jsonify(error.model_dump()), 403

            # Build response
            tier_results = None
            if decision.validator_results:
                tier_results = [
                    ValidationTierResult(
                        validator_name=vr.validator_name,
                        score=round(vr.score, 4),
                        passed=vr.passed,
                        evidence=vr.evidence,
                        latency_ms=round(vr.latency_ms, 2),
                        error=vr.error,
                    )
                    for vr in decision.validator_results
                ]

            action_enforcement = None
            if decision.action_enforcement:
                action_enforcement = ActionEnforcementInfo(
                    enforced=decision.action_enforcement.enforced,
                    allowed=decision.action_enforcement.allowed,
                    user_task=decision.action_enforcement.user_task,
                    action_plan=decision.action_enforcement.action_plan,
                    reason=decision.action_enforcement.reason,
                )

            response = ValidationDecision(
                decision=decision.decision,
                risk_score=round(decision.risk_score, 4),
                confidence=round(decision.confidence, 4),
                output=decision.output,
                evidence=decision.evidence,
                suggested_fix=decision.suggested_fix,
                tier_results=tier_results,
                latency_ms=round(decision.latency_ms, 2),
                policy_name=decision.policy_name,
                prompt_injection_risk=round(decision.prompt_injection_risk, 4),
                action_enforcement=action_enforcement,
            )

            logger.info(
                f"Validation result: decision={response.decision}, "
                f"risk={response.risk_score:.3f}, latency={response.latency_ms:.1f}ms"
            )

            return jsonify(response.model_dump(exclude_none=True)), 200

        except ValueError as e:
            # Invalid input to Guard
            logger.warning(f"Validation input error: {e}")
            error = ErrorResponse(
                error=f"Invalid validation input: {str(e)}",
                code="VALIDATION_ERROR",
                details={"message": str(e)},
            )
            return jsonify(error.model_dump()), 422

        except Exception as e:
            logger.error(f"Validation error: {e}", exc_info=True)
            error = ErrorResponse(
                error="Validation failed",
                code="SERVER_ERROR",
                details={"message": str(e)},
            )
            return jsonify(error.model_dump()), 500

    @bp.route("/batch", methods=["POST"])
    @log_request
    def batch_validate() -> tuple:
        """Batch validate multiple outputs.

        Request body:
            BatchValidateRequest with array of validate requests

        Returns:
            BatchValidateResponse with array of ValidationDecision results
        """
        try:
            # Parse request
            req_data = request.get_json()
            if not req_data:
                error = ErrorResponse(
                    error="Request body must be valid JSON",
                    code="BAD_REQUEST",
                    details={"received": "null"},
                )
                return jsonify(error.model_dump()), 400

            req = BatchValidateRequest(**req_data)

            logger.info(
                f"Batch validation: {len(req.validations)} items, "
                f"max_parallel={req.max_parallel}"
            )

            # Process validations
            batch_start = time.time()
            results = []
            failed_count = 0

            for idx, item in enumerate(req.validations):
                try:
                    # Get Guard with specified policy
                    policy = item.policy or "default"
                    guard = get_guard(policy=policy)

                    if guard is None:
                        logger.error(f"[Batch {idx}] Guard not available")
                        failed_count += 1
                        continue

                    # Run validation
                    try:
                        decision = guard.validate(
                            prompt=item.prompt,
                            output=item.output,
                            context=item.context,
                            domain=item.domain or config.DEFAULT_DOMAIN,
                            action_plan=item.action_plan,
                            user_task=item.user_task,
                        )
                    except IntentViolationError as e:
                        logger.warning(f"[Batch {idx}] ArmorIQ blocked: {e.reason}")
                        failed_count += 1
                        continue

                    # Build result
                    tier_results = None
                    if decision.validator_results:
                        tier_results = [
                            ValidationTierResult(
                                validator_name=vr.validator_name,
                                score=round(vr.score, 4),
                                passed=vr.passed,
                                evidence=vr.evidence,
                                latency_ms=round(vr.latency_ms, 2),
                                error=vr.error,
                            )
                            for vr in decision.validator_results
                        ]

                    action_enforcement = None
                    if decision.action_enforcement:
                        action_enforcement = ActionEnforcementInfo(
                            enforced=decision.action_enforcement.enforced,
                            allowed=decision.action_enforcement.allowed,
                            user_task=decision.action_enforcement.user_task,
                            action_plan=decision.action_enforcement.action_plan,
                            reason=decision.action_enforcement.reason,
                        )

                    result = ValidationDecision(
                        decision=decision.decision,
                        risk_score=round(decision.risk_score, 4),
                        confidence=round(decision.confidence, 4),
                        output=decision.output,
                        evidence=decision.evidence,
                        suggested_fix=decision.suggested_fix,
                        tier_results=tier_results,
                        latency_ms=round(decision.latency_ms, 2),
                        policy_name=decision.policy_name,
                        prompt_injection_risk=round(decision.prompt_injection_risk, 4),
                        action_enforcement=action_enforcement,
                    )

                    results.append(result)
                    logger.debug(
                        f"[Batch {idx}] decision={result.decision}, risk={result.risk_score:.3f}"
                    )

                except ValueError as e:
                    logger.warning(f"[Batch {idx}] Input error: {e}")
                    failed_count += 1
                except Exception as e:
                    logger.error(f"[Batch {idx}] Validation error: {e}", exc_info=True)
                    failed_count += 1

            batch_elapsed = (time.time() - batch_start) * 1000

            response = BatchValidateResponse(
                results=results,
                total_time_ms=round(batch_elapsed, 2),
                processed_count=len(results),
                failed_count=failed_count,
            )

            logger.info(
                f"Batch complete: {len(results)} processed, {failed_count} failed, "
                f"total_time={batch_elapsed:.1f}ms"
            )

            return jsonify(response.model_dump(exclude_none=True)), 200

        except Exception as e:
            logger.error(f"Batch validation error: {e}", exc_info=True)
            error = ErrorResponse(
                error="Batch validation failed",
                code="SERVER_ERROR",
                details={"message": str(e)},
            )
            return jsonify(error.model_dump()), 500

    return bp
