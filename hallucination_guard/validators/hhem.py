"""Tier 3: HHEM 2.1-Open Faithfulness Classifier.

Uses vectara/hallucination_evaluation_model for faithfulness classification.
Target latency: <80ms. Lazy-loads model on first use.
"""

import logging
import os
import time
from typing import Optional
import threading

from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

_HHEM_MODEL = None
_HHEM_TOKENIZER = None
_HHEM_MODEL_LOCK = threading.Lock()
_HHEM_MODEL_LOAD_ERROR: Optional[str] = None
_HHEM_MODEL_LOAD_ATTEMPTED = False


def _get_hhem_model():
    global _HHEM_MODEL, _HHEM_TOKENIZER, _HHEM_MODEL_LOAD_ERROR, _HHEM_MODEL_LOAD_ATTEMPTED
    if _HHEM_MODEL is not None and _HHEM_TOKENIZER is not None:
        return _HHEM_TOKENIZER, _HHEM_MODEL, None

    with _HHEM_MODEL_LOCK:
        if _HHEM_MODEL is not None and _HHEM_TOKENIZER is not None:
            return _HHEM_TOKENIZER, _HHEM_MODEL, None
        try:
            model_name = "vectara/hallucination_evaluation_model"
            logger.info(f"Loading HHEM model (singleton): {model_name}")
            tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
            model = AutoModelForSequenceClassification.from_pretrained(model_name, trust_remote_code=True)
            model.eval()
            _HHEM_MODEL = model
            _HHEM_TOKENIZER = tokenizer
            _HHEM_MODEL_LOAD_ERROR = None
            _HHEM_MODEL_LOAD_ATTEMPTED = True
            logger.info("HHEM singleton model loaded successfully")
            return tokenizer, model, None
        except Exception as e:  # pragma: no cover - defensive
            _HHEM_MODEL = None
            _HHEM_TOKENIZER = None
            _HHEM_MODEL_LOAD_ERROR = str(e)
            _HHEM_MODEL_LOAD_ATTEMPTED = True
            logger.warning(f"Failed to load HHEM singleton model: {e}")
            return None, None, _HHEM_MODEL_LOAD_ERROR


def preload_hhem() -> bool:
    """Eagerly load the HHEM model singleton.

    Returns:
        True if the model is available after the call, False otherwise.
    """
    tokenizer, model, error = _get_hhem_model()
    return tokenizer is not None and model is not None and error is None

from hallucination_guard.validators.base import (
    BaseValidator,
    ValidationInput,
    ValidationResult,
)

logger = logging.getLogger(__name__)


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
        
        # Uses process-wide singleton model/tokenizer (see module-level cache).
        # Instance keeps only threshold/timeout configuration.
    
    def is_available(self) -> bool:
        """Check if HHEM validator can run.
        
        Returns:
            False if HG_DISABLE_HHEM is set or transformers/torch unavailable,
            True otherwise.
        """
        # Check environment variable first
        if os.getenv("HG_DISABLE_HHEM", "false").lower() == "true":
            return False
        
        # Check for required dependencies
        try:
            import transformers  # noqa: F401
            import torch  # noqa: F401
            return True
        except ImportError:
            return False
    
    def _load_model(self):
        """Get or load the shared HHEM model and tokenizer.

        Returns:
            Tuple (tokenizer, model, error). If error is not None, tokenizer/model
            will be None and caller should treat the validator as unavailable.
        """
        return _get_hhem_model()
    
    def validate(self, input: ValidationInput) -> ValidationResult:
        """Validate output faithfulness using HHEM model.
        
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
                error="HHEM disabled"
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
                error="No context"
            )
        
        # Run inference
        try:
            tokenizer, model, error = self._load_model()
            if error is not None or tokenizer is None or model is None:
                # Cache tokenizer/model on the instance for faster access after singleton load
                self.tokenizer = tokenizer if tokenizer is not None else None
                self.model = model if model is not None else None
                latency_ms = (time.perf_counter() - start_time) * 1000
                error_msg = error or "Model load failed"
                return ValidationResult(
                    validator_name="hhem",
                    score=0.5,
                    passed=False,
                    evidence=f"Model unavailable: {error_msg}",
                    latency_ms=latency_ms,
                    error=error_msg,
                )

            # Format input as required by HHEM model
            # The model expects: "Context: {context}\nOutput: {output}"
            formatted_input = f"Context: {input.context}\nOutput: {input.output}"
            
            # Tokenize
            inputs = self.tokenizer(
                formatted_input,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True
            )
            
            # Run inference
            with torch.no_grad():
                outputs = self.model(**inputs)
                logits = outputs.logits
                
                # HHEM model outputs binary classification: [hallucinated, faithful]
                # Apply softmax to get probabilities
                probs = torch.nn.functional.softmax(logits, dim=-1)
                
                # Extract faithfulness probability (second class)
                faithfulness_score = probs[0][1].item()
            
            latency_ms = (time.perf_counter() - start_time) * 1000
            passed = faithfulness_score >= self.threshold
            
            return ValidationResult(
                validator_name="hhem",
                score=faithfulness_score,
                passed=passed,
                evidence=f"HHEM faithfulness score: {faithfulness_score:.3f} (threshold: {self.threshold:.3f})",
                latency_ms=latency_ms
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
                error=str(e)
            )
