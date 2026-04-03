"""Tier Phase 2: Lynx 8B Advanced Reasoning Validator.

Placeholder for PatronusAI/Llama-3-Patronus-Lynx-8B-Instruct.
Requires GPU (16GB VRAM) - not available for MVP.
Always returns unavailable to prevent runtime errors on CPU-only systems.
"""

import logging

from hallucination_guard.validators.base import (
    BaseValidator,
    ValidationInput,
    ValidationResult,
)

logger = logging.getLogger(__name__)


class LynxValidator(BaseValidator):
    """Lynx 8B placeholder validator (Phase 2).
    
    Lynx is a 16GB GPU-required model for advanced reasoning about
    hallucinations. This placeholder always returns unavailable since
    GPU support is deferred to Phase 2.
    
    To enable Lynx in the future, override is_available() to check for
    CUDA availability and _load_model() to load from HuggingFace.
    """
    
    def __init__(self, config: dict):
        """Initialize Lynx validator placeholder.
        
        Args:
            config: Configuration dict (unused for placeholder)
        """
        super().__init__(config)
    
    def is_available(self) -> bool:
        """Lynx is not available for MVP.
        
        Returns:
            False (GPU not available, Phase 2 only)
        """
        return False
    
    def validate(self, input: ValidationInput) -> ValidationResult:
        """Return neutral score since Lynx is not available.
        
        Args:
            input: ValidationInput (unused, validator unavailable)
        
        Returns:
            ValidationResult with neutral score and unavailable evidence
        """
        return ValidationResult(
            validator_name="lynx",
            score=0.5,
            passed=False,
            evidence="Lynx not available for MVP (Phase 2, requires GPU)",
            latency_ms=0.0,
        )
