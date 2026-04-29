"""Tier 1 Heuristics Validator.

Fast deterministic checks for hallucination detection.
Target latency: <5ms (no model inference).

Implements three sub-checks:
1. Context coverage ratio - fraction of output tokens present in context
2. Entity overlap - capitalized n-gram overlap (proxy for named entities)
3. Length anomaly - penalizes outputs much longer than context

Final score is weighted average: coverage=0.5, entity=0.3, length=0.2
"""

import re
import time
from typing import Optional, Set

from .base import BaseValidator, ValidationInput, ValidationResult


class HeuristicsValidator(BaseValidator):
    """Tier 1 validator using fast heuristic checks.
    
    No model dependencies - pure deterministic validation.
    Gracefully handles missing context by returning neutral scores.
    """
    
    # Weights for score aggregation
    COVERAGE_WEIGHT = 0.5
    ENTITY_WEIGHT = 0.3
    LENGTH_WEIGHT = 0.2
    
    # Regex for capitalized n-grams (proxy for named entities)
    ENTITY_PATTERN = re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b')
    
    def __init__(self, config: dict):
        """Initialize heuristics validator.
        
        Args:
            config: Configuration dict with 'threshold' key (default 0.5)
        """
        super().__init__(config)
        self.threshold = config.get("threshold", 0.5)
    
    def is_available(self) -> bool:
        """Always available - no external dependencies.
        
        Returns:
            True (heuristics validator has no runtime dependencies)
        """
        return True
    
    def validate(self, input: ValidationInput) -> ValidationResult:
        """Validate output using heuristic checks.
        
        Args:
            input: ValidationInput with prompt, output, and optional context
        
        Returns:
            ValidationResult with aggregated score and evidence
        """
        start_time = time.perf_counter()
        
        try:
            # Run three sub-checks
            coverage_score = self._context_coverage_ratio(input.output, input.context)
            entity_score = self._entity_overlap_check(input.output, input.context)
            length_score = self._length_anomaly_check(input.output, input.context)
            
            # Weighted aggregation
            final_score = (
                self.COVERAGE_WEIGHT * coverage_score +
                self.ENTITY_WEIGHT * entity_score +
                self.LENGTH_WEIGHT * length_score
            )
            
            # Ensure score is in valid range
            final_score = max(0.0, min(1.0, final_score))
            
            # Build evidence string
            evidence = (
                f"Heuristics check: coverage={coverage_score:.2f}, "
                f"entity={entity_score:.2f}, length={length_score:.2f}, "
                f"final={final_score:.2f}"
            )
            
            # Add context handling note if applicable
            if input.context is None:
                evidence += " (no context provided, using neutral scores)"
            
            latency_ms = (time.perf_counter() - start_time) * 1000
            
            return ValidationResult(
                validator_name="heuristics",
                score=final_score,
                passed=final_score >= self.threshold,
                evidence=evidence,
                latency_ms=latency_ms
            )
        
        except Exception as e:
            # Graceful degradation - return neutral score
            latency_ms = (time.perf_counter() - start_time) * 1000
            return ValidationResult(
                validator_name="heuristics",
                score=0.5,
                passed=False,
                evidence=f"Heuristics check failed, returning neutral score",
                latency_ms=latency_ms,
                error=str(e)
            )
    
    def _context_coverage_ratio(self, output: str, context: Optional[str]) -> float:
        """Calculate fraction of output tokens present in context.
        
        Args:
            output: Generated text to validate
            context: Reference context (optional)
        
        Returns:
            Score in [0.0, 1.0] where 1.0 = all output tokens in context
            Returns 0.5 if context is None
        """
        if context is None:
            return 0.5
        
        # Simple tokenization: lowercase and split
        output_tokens = set(output.lower().split())
        context_tokens = set(context.lower().split())
        
        if not output_tokens:
            return 1.0  # Empty output is technically covered
        
        # Count overlap
        overlap = output_tokens.intersection(context_tokens)
        coverage = len(overlap) / len(output_tokens)
        
        return coverage
    
    def _entity_overlap_check(self, output: str, context: Optional[str]) -> float:
        """Check overlap of capitalized n-grams (proxy for named entities).
        
        Args:
            output: Generated text to validate
            context: Reference context (optional)
        
        Returns:
            Score in [0.0, 1.0] where 1.0 = all output entities in context
            Returns 0.5 if context is None
        """
        if context is None:
            return 0.5
        
        # Extract capitalized n-grams
        output_entities = set(self.ENTITY_PATTERN.findall(output))
        context_entities = set(self.ENTITY_PATTERN.findall(context))
        
        if not output_entities:
            return 1.0  # No entities to check
        
        # Count overlap
        overlap = output_entities.intersection(context_entities)
        entity_coverage = len(overlap) / len(output_entities)
        
        return entity_coverage
    
    def _length_anomaly_check(self, output: str, context: Optional[str]) -> float:
        """Penalize outputs much longer than context.
        
        Args:
            output: Generated text to validate
            context: Reference context (optional)
        
        Returns:
            Score in [0.0, 1.0] where 1.0 = length is reasonable
            Returns 1.0 if context is None
        """
        if context is None:
            return 1.0
        
        output_len = len(output)
        context_len = len(context)
        
        if context_len == 0:
            # Empty context - penalize non-empty output
            return 0.0 if output_len > 0 else 1.0
        
        # Calculate length ratio
        length_ratio = output_len / context_len
        
        # Penalize if output is more than 2x context length
        # score = 1.0 - min(1.0, max(0.0, length_ratio - 1.0))
        if length_ratio <= 1.0:
            return 1.0
        else:
            penalty = min(1.0, length_ratio - 1.0)
            return 1.0 - penalty
