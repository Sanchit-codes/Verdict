"""Tier 2: Embedding-based semantic similarity validator.

Uses sentence-transformers to compute cosine similarity between context and output.
Target latency: <30ms. Model is lazy-loaded on first validation call.
"""

import logging
import os
import time
import threading
from typing import Optional, Tuple, Any

import numpy as np

from hallucination_guard.validators.base import (
    BaseValidator,
    ValidationInput,
    ValidationResult,
)

logger = logging.getLogger(__name__)

# Module-level singleton for embedding model
_EMBEDDING_MODEL = None
_EMBEDDING_MODEL_LOCK = threading.Lock()
_EMBEDDING_MODEL_LOAD_ERROR: Optional[str] = None
_EMBEDDING_MODEL_LOAD_ATTEMPTED = False


def _get_embedding_model() -> Tuple[Any, Optional[str]]:
    """Load or return the cached embedding model singleton.

    Returns:
        Tuple of (model, error). If error is not None, model will be None.
    """
    global _EMBEDDING_MODEL, _EMBEDDING_MODEL_LOAD_ERROR, _EMBEDDING_MODEL_LOAD_ATTEMPTED

    if _EMBEDDING_MODEL is not None:
        return _EMBEDDING_MODEL, None

    with _EMBEDDING_MODEL_LOCK:
        # Double-check after acquiring lock
        if _EMBEDDING_MODEL is not None:
            return _EMBEDDING_MODEL, None

        if _EMBEDDING_MODEL_LOAD_ATTEMPTED and _EMBEDDING_MODEL is None:
            return None, _EMBEDDING_MODEL_LOAD_ERROR

        try:
            from sentence_transformers import SentenceTransformer

            model_name = "sentence-transformers/all-MiniLM-L6-v2"
            logger.info(f"Loading embedding model (singleton): {model_name}")
            model = SentenceTransformer(model_name)
            _EMBEDDING_MODEL = model
            _EMBEDDING_MODEL_LOAD_ERROR = None
            _EMBEDDING_MODEL_LOAD_ATTEMPTED = True
            logger.info("Embedding singleton model loaded successfully")
            return model, None
        except ImportError as e:
            _EMBEDDING_MODEL = None
            _EMBEDDING_MODEL_LOAD_ERROR = f"sentence-transformers not installed: {e}"
            _EMBEDDING_MODEL_LOAD_ATTEMPTED = True
            logger.warning(_EMBEDDING_MODEL_LOAD_ERROR)
            return None, _EMBEDDING_MODEL_LOAD_ERROR
        except Exception as e:
            _EMBEDDING_MODEL = None
            _EMBEDDING_MODEL_LOAD_ERROR = f"Failed to load embedding model: {e}"
            _EMBEDDING_MODEL_LOAD_ATTEMPTED = True
            logger.warning(_EMBEDDING_MODEL_LOAD_ERROR)
            return None, _EMBEDDING_MODEL_LOAD_ERROR


def preload_embedding() -> bool:
    """Eagerly load the embedding model singleton.

    Returns:
        True if the model is available after the call, False otherwise.
    """
    model, error = _get_embedding_model()
    return model is not None and error is None


class EmbeddingValidator(BaseValidator):
    """Embedding-based semantic similarity validator.
    
    Computes cosine similarity between context and output embeddings using
    sentence-transformers all-MiniLM-L6-v2 model (~80MB).
    
    Model is lazy-loaded on first validate() call to avoid startup penalty.
    Gracefully degrades on import errors or model loading failures.
    
    Uses process-wide singleton model (see module-level cache).
    Instance keeps only threshold/timeout configuration.
    """
    
    def __init__(self, config: dict):
        """Initialize embedding validator.
        
        Args:
            config: Validator configuration dict. Expected keys:
                - threshold (float): Score threshold for passing (default: 0.7)
                - timeout_ms (float): Not used, for consistency with other validators
        """
        super().__init__(config)
        self.threshold = config.get("threshold", 0.7)
        self.timeout_ms = config.get("timeout_ms", 30)
        
        # Uses process-wide singleton model (see module-level cache).
        # Instance keeps only threshold/timeout configuration.
    
    def is_available(self) -> bool:
        """Check if embedding validator can run.
        
        Returns:
            False if sentence-transformers unavailable, or if disabled via env var,
            True otherwise.
        """
        # Check environment variable first
        if os.getenv("HG_DISABLE_EMBEDDING", "false").lower() == "true":
            return False
        
        # Check for required dependencies
        try:
            import sentence_transformers  # noqa: F401
            return True
        except ImportError:
            return False
    
    def _load_model(self) -> Tuple[Any, Optional[str]]:
        """Get or load the shared embedding model.

        Returns:
            Tuple (model, error). If error is not None, model will be None
            and caller should treat the validator as unavailable.
        """
        return _get_embedding_model()
    
    def _compute_cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Compute cosine similarity between two vectors.
        
        Args:
            vec1: First embedding vector
            vec2: Second embedding vector
        
        Returns:
            Cosine similarity in range [-1, 1], normalized to [0, 1]
        """
        # Compute cosine similarity
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.5  # Neutral score for zero vectors
        
        cosine_sim = dot_product / (norm1 * norm2)
        
        # Normalize from [-1, 1] to [0, 1]
        # -1 (opposite) -> 0, 0 (orthogonal) -> 0.5, 1 (same) -> 1
        normalized_score = (cosine_sim + 1.0) / 2.0
        
        return float(normalized_score)
    
    def validate(self, input: ValidationInput) -> ValidationResult:
        """Validate output against context using embedding similarity.
        
        Args:
            input: ValidationInput containing prompt, output, context, and metadata
        
        Returns:
            ValidationResult with cosine similarity score in [0, 1] range
        """
        start_time = time.perf_counter()
        
        # Handle missing context
        if input.context is None or input.context.strip() == "":
            latency_ms = (time.perf_counter() - start_time) * 1000
            return ValidationResult(
                validator_name="embedding",
                score=0.5,
                passed=False,
                evidence="No context provided, skipping embedding similarity check",
                latency_ms=latency_ms,
            )
        
        # Get singleton model
        model, error = self._load_model()
        
        # If model loading failed, return neutral score with error
        if model is None or error is not None:
            latency_ms = (time.perf_counter() - start_time) * 1000
            error_msg = error or "Model load failed"
            return ValidationResult(
                validator_name="embedding",
                score=0.5,
                passed=False,
                evidence=f"Model unavailable: {error_msg}",
                latency_ms=latency_ms,
                error=error_msg,
            )
        
        # Encode context and output
        try:
            # Encode both texts
            context_embedding = model.encode(
                input.context,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            output_embedding = model.encode(
                input.output,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            
            # Compute similarity
            similarity_score = self._compute_cosine_similarity(
                context_embedding,
                output_embedding,
            )
            
            # Ensure score is in valid range
            similarity_score = max(0.0, min(1.0, similarity_score))
            
            latency_ms = (time.perf_counter() - start_time) * 1000
            passed = similarity_score >= self.threshold
            
            return ValidationResult(
                validator_name="embedding",
                score=similarity_score,
                passed=passed,
                evidence=f"Embedding cosine similarity: {similarity_score:.3f}",
                latency_ms=latency_ms,
            )
        
        except Exception as e:
            # Graceful degradation on encoding errors
            latency_ms = (time.perf_counter() - start_time) * 1000
            error_msg = f"Embedding encoding failed: {type(e).__name__}: {e}"
            logger.warning(error_msg)
            
            return ValidationResult(
                validator_name="embedding",
                score=0.5,
                passed=False,
                evidence="Embedding computation failed, returning neutral score",
                latency_ms=latency_ms,
                error=error_msg,
            )
