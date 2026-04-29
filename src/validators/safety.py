"""Optional: Llama Guard Safety Validator.

Placeholder for safety content checks (complementary to faithfulness).
Disabled by default - can be enabled via policy configuration.
Always returns unavailable in MVP until needed.
"""

import logging

from verdict.validators.base import (
    BaseValidator,
    ValidationInput,
    ValidationResult,
)

logger = logging.getLogger(__name__)


class SafetyValidator(BaseValidator):
    """Safety content checks placeholder validator.
    
    Llama Guard 2 can complement HallucinationGuard by detecting harmful
    content (violence, hate speech, etc.). This placeholder is disabled
    by default since the primary focus is hallucination detection.
    
    To enable Safety in the future:
    1. Set enabled=true in policy YAML under validators.safety
    2. Implement _load_model() to load Llama Guard from HuggingFace
    3. Update is_available() to check transformers dependency
    """
    
    def __init__(self, config: dict):
        """Initialize Safety validator placeholder.
        
        Args:
            config: Configuration dict (unused for placeholder)
        """
        super().__init__(config)
    
    def is_available(self) -> bool:
        """Safety checks are disabled by default.
        
        Returns:
            False (safety checks disabled for MVP)
        """
        return False
    
    def validate(self, input: ValidationInput) -> ValidationResult:
        """Return neutral score since safety checks are disabled.
        
        Args:
            input: ValidationInput (unused, validator disabled)
        
        Returns:
            ValidationResult with neutral score and disabled evidence
        """
        return ValidationResult(
            validator_name="safety",
            score=0.5,
            passed=True,
            evidence="Safety checks disabled (complementary to hallucination detection)",
            latency_ms=0.0,
        )
