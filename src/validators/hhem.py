"""Tier 3: HHEM 2.1-Open Faithfulness Classifier.

Uses vectara/hallucination_evaluation_model for faithfulness classification.
Target latency: <80ms. Lazy-loads model on first use.

Uses the recommended model.predict() approach per Vectara's documentation:
https://huggingface.co/vectara/hallucination_evaluation_model
"""

import logging
import os
import time
from typing import Optional, Tuple, Any
import threading

from transformers import AutoModelForSequenceClassification

from verdict.validators.base import (
    BaseValidator,
    ValidationInput,
    ValidationResult,
)

logger = logging.getLogger(__name__)

_HHEM_MODEL = None
_HHEM_MODEL_LOCK = threading.Lock()
_HHEM_MODEL_LOAD_ERROR: Optional[str] = None
_HHEM_MODEL_LOAD_ATTEMPTED = False


def _get_hhem_model() -> Tuple[Any, Optional[str]]:
    """Load or return the cached HHEM model singleton.

    Uses the model.predict() approach recommended by Vectara, which doesn't
    require a separate tokenizer (the model handles tokenization internally).

    Returns:
        Tuple of (model, error). If error is not None, model will be None.
    """
    global _HHEM_MODEL, _HHEM_MODEL_LOAD_ERROR, _HHEM_MODEL_LOAD_ATTEMPTED

    if _HHEM_MODEL is not None:
        return _HHEM_MODEL, None

    with _HHEM_MODEL_LOCK:
        # Double-check after acquiring lock
        if _HHEM_MODEL is not None:
            return _HHEM_MODEL, None

        try:
            model_name = "vectara/hallucination_evaluation_model"
            logger.info(f"Loading HHEM model (singleton): {model_name}")
            model = AutoModelForSequenceClassification.from_pretrained(
                model_name, trust_remote_code=True
            )
            model.eval()
            _HHEM_MODEL = model
            _HHEM_MODEL_LOAD_ERROR = None
            _HHEM_MODEL_LOAD_ATTEMPTED = True
            logger.info("HHEM singleton model loaded successfully")
            return model, None
        except Exception as e:  # pragma: no cover - defensive
            _HHEM_MODEL = None
            _HHEM_MODEL_LOAD_ERROR = str(e)
            _HHEM_MODEL_LOAD_ATTEMPTED = True
            logger.warning(f"Failed to load HHEM singleton model: {e}")
            return None, _HHEM_MODEL_LOAD_ERROR


def preload_hhem() -> bool:
    """Eagerly load the HHEM model singleton.

    Returns:
        True if the model is available after the call, False otherwise.
    """
    model, error = _get_hhem_model()
    return model is not None and error is None


class HHEMValidator(BaseValidator):
    """HHEM 2.1-Open faithfulness classifier (Tier 3).
    
    Uses the vectara/hallucination_evaluation_model to classify whether
    generated output is faithful to the provided context.
    
    Model is lazy-loaded on first validate() call to avoid startup overhead.
    Respects HG_DISABLE_HHEM environment variable for fast testing mode.
    """
    
    def __init__(self, config: dict):
        """Initialize HHEM validator.
        
        Args:
            config: Configuration dict with keys:
                - threshold: Minimum faithfulness score (default 0.5)
                - timeout_ms: Max inference time in milliseconds
        """
        super().__init__(config)
        self.threshold = config.get("threshold", 0.5)
        self.timeout_ms = config.get("timeout_ms", 80)
        
        # Uses process-wide singleton model (see module-level cache).
        # Instance keeps only threshold/timeout configuration.

    def is_available(self) -> bool:
        """Check if HHEM validator can run.

        Returns:
            False if HG_DISABLE_HHEM is set or transformers unavailable,
            True otherwise.
        """
        # Check environment variable first
        if os.getenv("HG_DISABLE_HHEM", "false").lower() == "true":
            return False

        # Check for required dependencies
        try:
            import transformers  # noqa: F401

            return True
        except ImportError:
            return False

    def _load_model(self) -> Tuple[Any, Optional[str]]:
        """Get or load the shared HHEM model.

        Returns:
            Tuple (model, error). If error is not None, model will be None
            and caller should treat the validator as unavailable.
        """
        return _get_hhem_model()

    def validate(self, input: ValidationInput) -> ValidationResult:
        """Validate output faithfulness using HHEM model.

        Uses the model.predict() approach recommended by Vectara, which takes
        a list of (premise, hypothesis) tuples where:
        - premise = context (the source of truth)
        - hypothesis = output (the text to validate)

        Args:
            input: ValidationInput with prompt, output, and optional context

        Returns:
            ValidationResult with faithfulness score in [0, 1] where:
            - 1.0 = definitely faithful to context
            - 0.0 = definitely hallucinated
        """
        start_time = time.perf_counter()

        # Check if HHEM is disabled via environment variable
        if os.getenv("HG_DISABLE_HHEM", "false").lower() == "true":
            latency_ms = (time.perf_counter() - start_time) * 1000
            return ValidationResult(
                validator_name="hhem",
                score=0.5,
                passed=False,
                evidence="HHEM disabled via HG_DISABLE_HHEM environment variable",
                latency_ms=latency_ms,
                error="HHEM disabled",
            )

        # Handle missing context
        if input.context is None:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return ValidationResult(
                validator_name="hhem",
                score=0.5,
                passed=False,
                evidence="No context provided, cannot assess faithfulness",
                latency_ms=latency_ms,
                error="No context",
            )

        # Run inference
        try:
            model, error = self._load_model()
            if error is not None or model is None:
                latency_ms = (time.perf_counter() - start_time) * 1000
                error_msg = error or "Model load failed"
                logger.warning(f"HHEM validator returning neutral score (0.5): {error_msg}")
                return ValidationResult(
                    validator_name="hhem",
                    score=0.5,
                    passed=False,
                    evidence=f"Model unavailable: {error_msg}",
                    latency_ms=latency_ms,
                    error=error_msg,
                )

            # Use model.predict() approach per Vectara's recommendation
            # pairs is a list of (premise, hypothesis) tuples
            # premise = context (source of truth), hypothesis = output (to validate)
            pairs = [(input.context, input.output)]

            # model.predict() returns a tensor of scores
            # Score represents probability that hypothesis is faithful to premise
            scores = model.predict(pairs)
            faithfulness_score = scores[0].item()

            latency_ms = (time.perf_counter() - start_time) * 1000
            passed = faithfulness_score >= self.threshold

            return ValidationResult(
                validator_name="hhem",
                score=faithfulness_score,
                passed=passed,
                evidence=f"HHEM faithfulness score: {faithfulness_score:.3f} (threshold: {self.threshold:.3f})",
                latency_ms=latency_ms,
            )

        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            logger.warning(f"HHEM inference failed: {e}")

            # Graceful degradation: return neutral score
            return ValidationResult(
                validator_name="hhem",
                score=0.5,
                passed=False,
                evidence=f"Inference failed, returning neutral score: {str(e)[:100]}",
                latency_ms=latency_ms,
                error=str(e),
            )
