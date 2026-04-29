"""Pydantic schemas for Flask API request/response validation.

Matches TypeScript ValidationDecision and related types from Node.js SDK.
"""


from pydantic import BaseModel, Field


class ValidateRequest(BaseModel):
    """Request body for POST /api/validate endpoint."""

    prompt: str = Field(
        ..., min_length=1, description="User prompt or query that triggered generation"
    )
    output: str = Field(..., min_length=1, description="Model-generated text to validate")
    context: str | None = Field(
        None, description="Reference context (e.g., retrieved documents)"
    )
    policy: str | None = Field("default", description="Policy name to use for validation")
    domain: str | None = Field(None, description="Domain metadata (e.g., healthcare)")
    action_plan: str | None = Field(None, description="Optional action to enforce with ArmorIQ")
    user_task: str | None = Field(None, description="Declared task scope for ArmorIQ")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "prompt": "What is the capital of France?",
                "output": "The capital of France is Paris.",
                "context": "France is a country in Europe...",
                "policy": "default",
                "domain": "geography",
            }
        }


class ValidationTierResult(BaseModel):
    """Single validator result from the pipeline."""

    validator_name: str = Field(..., description="Name of the validator")
    score: float = Field(..., ge=0.0, le=1.0, description="Validation score in [0.0, 1.0]")
    passed: bool = Field(..., description="Whether validation passed threshold")
    evidence: str = Field(..., description="Human-readable explanation")
    latency_ms: float = Field(..., ge=0.0, description="Execution time in milliseconds")
    error: str | None = Field(None, description="Error message if validator failed")


class ActionEnforcementInfo(BaseModel):
    """ArmorIQ action enforcement result."""

    enforced: bool = Field(..., description="Whether ArmorIQ enforcement was performed")
    allowed: bool = Field(..., description="Whether action was allowed")
    user_task: str | None = Field(None, description="Declared task")
    action_plan: str | None = Field(None, description="Action that was enforced")
    reason: str | None = Field(None, description="Reason for block (if allowed=false)")


class ValidationDecision(BaseModel):
    """Response body for /api/validate and /api/batch endpoints.

    Matches TypeScript ValidationDecision type from Node.js SDK.
    """

    decision: str = Field(
        ...,
        description="Action to take: allow, block, regenerate, or abstain",
        pattern="^(allow|block|regenerate|abstain)$",
    )
    risk_score: float = Field(..., ge=0.0, le=1.0, description="Overall risk score in [0.0, 1.0]")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence in decision based on validator agreement"
    )
    output: str = Field(..., description="The validated output (same as input)")
    evidence: str = Field(..., description="Human-readable explanation of decision")
    suggested_fix: str | None = Field(
        None, description="Hint for regeneration if decision == regenerate"
    )
    tier_results: list[ValidationTierResult] | None = Field(
        None, description="Results from all validation tiers"
    )
    latency_ms: float = Field(..., ge=0.0, description="Total pipeline execution time")
    policy_name: str = Field(..., description="Name of the policy used")
    prompt_injection_risk: float = Field(
        ..., ge=0.0, le=1.0, description="Pre-computed prompt injection risk"
    )
    action_enforcement: ActionEnforcementInfo | None = Field(
        None, description="ArmorIQ enforcement result if applicable"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "decision": "allow",
                "risk_score": 0.15,
                "confidence": 0.92,
                "output": "The capital of France is Paris.",
                "evidence": "Output matches context with 0.95 cosine similarity.",
                "suggested_fix": None,
                "latency_ms": 48.5,
                "policy_name": "default",
                "prompt_injection_risk": 0.05,
                "action_enforcement": None,
                "tier_results": [
                    {
                        "validator_name": "heuristics",
                        "score": 0.85,
                        "passed": True,
                        "evidence": "Entity overlap: 1.0",
                        "latency_ms": 2.1,
                    },
                    {
                        "validator_name": "embedding",
                        "score": 0.95,
                        "passed": True,
                        "evidence": "Cosine similarity: 0.95",
                        "latency_ms": 15.3,
                    },
                ],
            }
        }


class BatchValidateRequest(BaseModel):
    """Request body for POST /api/batch endpoint."""

    validations: list[ValidateRequest] = Field(
        min_items=1, max_items=100, description="Array of validation requests"
    )
    max_parallel: int | None = Field(
        1, ge=1, le=10, description="Max concurrent validations (default: 1, sequential)"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "validations": [
                    {
                        "prompt": "What is 2+2?",
                        "output": "2+2 equals 4.",
                        "context": "Basic arithmetic.",
                    },
                    {
                        "prompt": "What is the capital of France?",
                        "output": "The capital of France is Paris.",
                        "context": "France is a country...",
                    },
                ],
                "max_parallel": 1,
            }
        }


class BatchValidateResponse(BaseModel):
    """Response body for POST /api/batch endpoint."""

    results: list[ValidationDecision] = Field(
        ..., description="Validation decision for each request"
    )
    total_time_ms: float = Field(..., ge=0.0, description="Total batch processing time")
    processed_count: int = Field(..., ge=0, description="Number of validations processed")
    failed_count: int = Field(..., ge=0, description="Number of validations that failed")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "results": [
                    {
                        "decision": "allow",
                        "risk_score": 0.1,
                        "confidence": 0.95,
                        "output": "2+2 equals 4.",
                        "evidence": "Simple arithmetic, low hallucination risk.",
                        "latency_ms": 35.2,
                        "policy_name": "default",
                        "prompt_injection_risk": 0.0,
                    }
                ],
                "total_time_ms": 150.5,
                "processed_count": 2,
                "failed_count": 0,
            }
        }


class HealthResponse(BaseModel):
    """Response body for GET /api/health endpoint."""

    status: str = Field(
        ..., description="Health status: healthy or degraded", pattern="^(healthy|degraded)$"
    )
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    models_loaded: dict[str, bool] = Field(
        ..., description="Status of loaded models (heuristics, embedding, hhem)"
    )
    guard_available: bool = Field(..., description="Whether Guard class is available")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "status": "healthy",
                "timestamp": "2024-04-05T12:34:56Z",
                "models_loaded": {
                    "heuristics": True,
                    "embedding": True,
                    "hhem": True,
                },
                "guard_available": True,
            }
        }


class VersionResponse(BaseModel):
    """Response body for GET /api/version endpoint."""

    version: str = Field(..., description="Server version")
    guard_version: str = Field(..., description="HallucinationGuard SDK version")
    python_version: str = Field(..., description="Python version")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "version": "1.0.0",
                "guard_version": "0.1.0",
                "python_version": "3.10.0",
            }
        }


class ErrorResponse(BaseModel):
    """Standard error response format."""

    error: str = Field(..., description="Error message")
    code: str = Field(..., description="Error code (e.g., VALIDATION_ERROR, SERVER_ERROR)")
    details: dict | None = Field(None, description="Additional error context")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "error": "Invalid request: prompt is required",
                "code": "VALIDATION_ERROR",
                "details": {"field": "prompt", "reason": "min_length=1"},
            }
        }


class GenerateRequest(BaseModel):
    """Request body for POST /api/generate endpoint.

    Combines user prompt with optional context and configuration
    for Gemini-based generation followed by HallucinationGuard validation.
    """

    prompt: str = Field(
        ..., min_length=1, description="User prompt or query for text generation"
    )
    context: str | None = Field(
        None,
        description="Optional reference context (e.g., retrieved documents) to ground generation",
    )
    policy: str | None = Field(
        "default", description="HallucinationGuard policy to use for validation"
    )
    domain: str | None = Field(
        None, description="Domain metadata for validation (e.g., healthcare, finance)"
    )
    model: str | None = Field(
        "gemini-2.5-flash", description="Gemini model variant to use for generation"
    )
    temperature: float | None = Field(
        0.7,
        ge=0.0,
        le=2.0,
        description="Sampling temperature for generation (0.0-2.0, default 0.7)",
    )
    max_tokens: int | None = Field(
        1024, ge=1, le=4096, description="Maximum output tokens (default 1024)"
    )

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "prompt": "What is the capital of France?",
                "context": "France is a country in Western Europe. It is known for its culture, cuisine, and landmarks.",
                "policy": "default",
                "domain": "geography",
                "model": "gemini-2.5-flash",
                "temperature": 0.7,
                "max_tokens": 256,
            }
        }


class GenerationLatency(BaseModel):
    """Latency breakdown for generation and validation stages."""

    generation_ms: float = Field(
        ..., ge=0.0, description="Time spent in Gemini generation"
    )
    validation_ms: float = Field(
        ..., ge=0.0, description="Time spent in HallucinationGuard validation"
    )
    total_ms: float = Field(..., ge=0.0, description="Total end-to-end time")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {"generation_ms": 250.5, "validation_ms": 45.2, "total_ms": 295.7}
        }


class GenerateResponse(BaseModel):
    """Response body for POST /api/generate endpoint.

    Combines generated text with full HallucinationGuard validation results
    and detailed latency measurements.
    """

    generated_text: str = Field(..., description="Text generated by Gemini model")
    decision: str = Field(
        ...,
        description="HallucinationGuard decision (allow, block, regenerate, abstain)",
        pattern="^(allow|block|regenerate|abstain)$",
    )
    risk_score: float = Field(
        ..., ge=0.0, le=1.0, description="Hallucination risk score in [0.0, 1.0]"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence in validation decision"
    )
    evidence: str = Field(
        ..., description="Human-readable explanation of validation decision"
    )
    latency_ms: GenerationLatency = Field(
        ..., description="Detailed latency breakdown for generation and validation"
    )
    tier_results: list[ValidationTierResult] | None = Field(
        None, description="Results from all validation tiers"
    )
    policy_name: str = Field(..., description="Policy used for validation")
    model: str = Field(..., description="Gemini model used for generation")

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "generated_text": "The capital of France is Paris, a major city located in northern-central France.",
                "decision": "allow",
                "risk_score": 0.12,
                "confidence": 0.94,
                "evidence": "Generated text aligns well with provided context (0.93 cosine similarity).",
                "latency_ms": {
                    "generation_ms": 250.5,
                    "validation_ms": 45.2,
                    "total_ms": 295.7,
                },
                "tier_results": [
                    {
                        "validator_name": "heuristics",
                        "score": 0.85,
                        "passed": True,
                        "evidence": "Entity overlap: 1.0",
                        "latency_ms": 2.1,
                    },
                    {
                        "validator_name": "embedding",
                        "score": 0.93,
                        "passed": True,
                        "evidence": "Cosine similarity: 0.93",
                        "latency_ms": 15.3,
                    },
                ],
                "policy_name": "default",
                "model": "gemini-2.5-flash",
            }
        }
