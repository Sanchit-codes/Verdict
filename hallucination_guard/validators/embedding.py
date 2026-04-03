"""Tier 2: Embedding-based semantic similarity validator.

Uses sentence-transformers to compute cosine similarity between context and output.
Target latency: <30ms. Model is lazy-loaded on first validation call.
"""

import logging
import time
from typing import Optional

import numpy as np

from hallucination_guard.validators.base import (
    BaseValidator,
    ValidationInput,
    ValidationResult,
)

logger = logging.getLogger(__name__)


class EmbeddingValidator(BaseValidator):
    """Embedding-based semantic similarity validator.
    
    Computes cosine similarity between context and output embeddings using
    sentence-transformers all-MiniLM-L6-v2 model (~80MB).
    
    Model is lazy-loaded on first validate() call to avoid startup penalty.
    Gracefully degrades on import errors or model loading failures.
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
        self.model = None  # Lazy-loaded on first validate() call
        self._model_load_failed = False
        self._load_error_msg: Optional[str] = None
    
    def is_available(self) -> bool:
        """Check if sentence-transformers is available.
        
        Returns:
            True if sentence-transformers can be imported, False otherwise
        """
        try:
            import sentence_transformers  # noqa: F401
            return True
        except ImportError:
            return False
    
    def _load_model(self):
        """Lazy-load the sentence-transformer model.
        
        Sets self.model to the loaded model, or leaves it None and sets
        self._model_load_failed if loading fails.
        """
        if self.model is not None:
            return  # Already loaded
        
        if self._model_load_failed:
            return  # Already tried and failed
        
        try:
            from sentence_transformers import SentenceTransformer
            
            logger.info("Loading sentence-transformers model: all-MiniLM-L6-v2")
            self.model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
            logger.info("Embedding model loaded successfully")
        except ImportError as e:
            self._model_load_failed = True
            self._load_error_msg = f"sentence-transformers not installed: {e}"
            logger.warning(self._load_error_msg)
        except Exception as e:
            self._model_load_failed = True
            self._load_error_msg = f"Failed to load embedding model: {e}"
            logger.warning(self._load_error_msg)
    
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
        
        # Lazy-load model
        self._load_model()
        
        # If model loading failed, return neutral score with error
        if self.model is None:
            latency_ms = (time.perf_counter() - start_time) * 1000
            return ValidationResult(
                validator_name="embedding",
                score=0.5,
                passed=False,
                evidence="Embedding model unavailable",
                latency_ms=latency_ms,
                error=self._load_error_msg,
            )
        
        # Encode context and output
        try:
            # Encode both texts
            context_embedding = self.model.encode(
                input.context,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
            output_embedding = self.model.encode(
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
