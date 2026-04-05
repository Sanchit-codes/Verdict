"""Tier 0: Content classifier validator.

Classifies content as factual vs non-factual to determine if validation is needed.
Non-factual content (greetings, questions, acknowledgments) bypasses expensive tiers.
"""

import re
import logging
import time
from typing import Optional

from hallucination_guard.validators.base import (
    BaseValidator,
    ValidationInput,
    ValidationResult,
)

logger = logging.getLogger(__name__)

# Patterns for non-factual content that should skip validation
NON_FACTUAL_PATTERNS = [
    # Greetings
    r'^(hi|hello|hey|good\s+(morning|afternoon|evening|day))',
    r'^what\'s\s+up',
    r'^how\s+(are\s+you|do\s+you\s+do|have\s+you\s+been)',
    r'^nice\s+to\s+meet\s+you',
    
    # Acknowledgments
    r'^(thank\s+you|thanks|thankyou)',
    r'^ok|okay|alright|sure|got\s+it',
    r'^yes|no|yeah|yep|nope',
    
    # Pure questions without claims
    r'^(can\s+you|could\s+you|would\s+you|do\s+you)',
    r'^what\s+is\s+.*\?$',
    r'^how\s+(do|can|should|would|might)',
    
    # Short responses
    r'^.{0,10}$',  # Very short responses
]

class ContentClassifierValidator(BaseValidator):
    """Classifies content to determine if validation is needed.
    
    Non-factual content like greetings, acknowledgments, and pure questions
    should pass validation without running expensive ML models.
    """
    
    def __init__(self, config: dict):
        """Initialize content classifier.
        
        Args:
            config: Configuration dict with optional 'skip_validation_patterns'
        """
        super().__init__(config)
        self.skip_patterns = config.get('skip_validation_patterns', NON_FACTUAL_PATTERNS)
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.skip_patterns]
    
    def validate(self, input: ValidationInput) -> ValidationResult:
        """Classify content and determine if validation should be skipped.
        
        Returns:
            score=1.0 (allow) for non-factual content that should skip validation
            score=0.5 (neutral) for content that needs normal validation
        """
        start_time = time.perf_counter()
        
        # Clean the output for pattern matching
        output_clean = input.output.strip().lower()
        
        # Check if output matches any non-factual patterns
        for pattern in self.compiled_patterns:
            if pattern.match(output_clean):
                latency_ms = (time.perf_counter() - start_time) * 1000
                return ValidationResult(
                    validator_name="content_classifier",
                    score=1.0,  # Allow non-factual content
                    passed=True,
                    evidence=f"Non-factual content detected ('{input.output[:50]}...') - skipping validation",
                    latency_ms=latency_ms,
                    metadata={"content_type": "non_factual", "skip_validation": True}
                )
        
        # Content appears factual - needs normal validation
        latency_ms = (time.perf_counter() - start_time) * 1000
        return ValidationResult(
            validator_name="content_classifier",
            score=0.5,  # Neutral - proceed with validation
            passed=True,
            evidence=f"Factual content detected - proceeding with validation",
            latency_ms=latency_ms,
            metadata={"content_type": "factual", "skip_validation": False}
        )
    
    def is_available(self) -> bool:
        """Always available - no dependencies."""
        return True
