"""Base validator interface and schemas.

All validators must inherit from BaseValidator and implement the validate() method.
ValidationInput and ValidationResult are immutable Pydantic models for type safety.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from hallucination_guard.prompts.schema import StructuredPrompt


class ValidationInput(BaseModel):
    """Input data for validation.
    
    Attributes:
        prompt: The user prompt or query
        output: The model-generated output to validate
        context: Optional reference context (e.g., retrieved documents)
        domain: Optional domain metadata (e.g., 'healthcare', 'finance')
        structured_prompt: Optional StructuredPrompt from prompt security analysis
    """
    
    prompt: str
    output: str
    context: Optional[str] = None
    domain: Optional[str] = None
    structured_prompt: Optional["StructuredPrompt"] = Field(
        default=None,
        description="Optional result from prompt security analysis (injection detection, intent classification)"
    )
    
    model_config = {"frozen": True}


class ValidationResult(BaseModel):
    """Result from a validator.
    
    Attributes:
        validator_name: Name of the validator that produced this result
        score: Faithfulness score in [0.0, 1.0] where 1.0 = faithful, 0.0 = hallucinated
        passed: Whether the validation passed the configured threshold
        evidence: Human-readable explanation of the decision
        latency_ms: Time taken to run validation in milliseconds
        error: Optional error message if validator failed gracefully
        metadata: Optional additional data from validator (e.g., structured_prompt, detailed results)
    """
    
    validator_name: str
    score: float = Field(ge=0.0, le=1.0)
    passed: bool
    evidence: str
    latency_ms: float = Field(ge=0.0)
    error: Optional[str] = None
    metadata: Optional[dict] = None
    
    model_config = {"frozen": True}
    
    @field_validator("score")
    @classmethod
    def validate_score_range(cls, v: float) -> float:
        """Ensure score is in valid range [0.0, 1.0]."""
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"Score must be between 0.0 and 1.0, got {v}")
        return v


class BaseValidator(ABC):
    """Abstract base class for all validators.
    
    Validators must implement the validate() method and can optionally
    override is_available() for runtime dependency checks (e.g., GPU, models).
    
    All validators should gracefully degrade on errors rather than crash
    the validation pipeline.
    """
    
    def __init__(self, config: dict):
        """Initialize validator with configuration.
        
        Args:
            config: Validator-specific configuration dict (e.g., threshold, timeout)
        """
        self.config = config
    
    @abstractmethod
    def validate(self, input: ValidationInput) -> ValidationResult:
        """Validate the output against the context.
        
        Args:
            input: ValidationInput containing prompt, output, context, and metadata
        
        Returns:
            ValidationResult with score, passed status, and evidence
        
        Note:
            Implementations MUST handle errors gracefully and return a
            ValidationResult with error field set rather than raising exceptions.
        """
        pass
    
    def is_available(self) -> bool:
        """Check if validator can run (models loaded, dependencies available).
        
        Returns:
            True if validator is ready to run, False otherwise
        
        Note:
            Override this method for validators that require GPU, specific models,
            or other runtime dependencies. Default implementation returns True.
        """
        return True
