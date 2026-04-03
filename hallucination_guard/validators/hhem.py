"""Tier 3: HHEM 2.1-Open Faithfulness Classifier.

Uses vectara/hallucination_evaluation_model for faithfulness classification.
Target latency: <80ms. Lazy-loads model on first use.
"""

import logging
import os
import time
from typing import Optional

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
        
        # Model and tokenizer are lazy-loaded on first validate() call
        self.model = None
        self.tokenizer = None
        self._model_load_attempted = False
        self._model_load_error: Optional[str] = None
    
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
    
    def _load_model(self) -> bool:
        """Lazy-load HHEM model and tokenizer.
        
        Returns:
            True if model loaded successfully, False otherwise.
        """
        if self._model_load_attempted:
            return self.model is not None
        
        self._model_load_attempted = True
        
        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification
            
            model_name = "vectara/hallucination_evaluation_model"
            logger.info(f"Loading HHEM model: {model_name}")
            
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
            self.model.eval()  # Set to evaluation mode
            
            logger.info("HHEM model loaded successfully")
            return True
            
        except Exception as e:
            self._model_load_error = str(e)
            logger.warning(f"Failed to load HHEM model: {e}")
            return False
    
    def validate(self, input: ValidationInput) -> ValidationResult:
        """Validate output faithfulness using HHEM model.
        
        Args:
            input: ValidationInput with prompt, output, and optional context
        
        Returns:
            ValidationResult with faithfulness score in [0, 1] where:
            - 1.0 = definitely faithful to context
            - 0.0 = definitely hallucinated
        """
        start_time = time.time()
        
        # Check if HHEM is disabled via environment variable
        if os.getenv("HG_DISABLE_HHEM", "false").lower() == "true":
            latency_ms = (time.time() - start_time) * 1000
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
            latency_ms = (time.time() - start_time) * 1000
            return ValidationResult(
                validator_name="hhem",
                score=0.5,
                passed=False,
                evidence="No context provided, cannot assess faithfulness",
                latency_ms=latency_ms,
                error="No context"
            )
        
        # Attempt to load model if not already loaded
        if not self._load_model():
            latency_ms = (time.time() - start_time) * 1000
            error_msg = self._model_load_error or "Model load failed"
            return ValidationResult(
                validator_name="hhem",
                score=0.5,
                passed=False,
                evidence=f"Model unavailable: {error_msg}",
                latency_ms=latency_ms,
                error=error_msg
            )
        
        # Run inference
        try:
            import torch
            
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
            
            latency_ms = (time.time() - start_time) * 1000
            passed = faithfulness_score >= self.threshold
            
            return ValidationResult(
                validator_name="hhem",
                score=faithfulness_score,
                passed=passed,
                evidence=f"HHEM faithfulness score: {faithfulness_score:.3f} (threshold: {self.threshold:.3f})",
                latency_ms=latency_ms
            )
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
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
