#!/usr/bin/env python3
"""
REST API Request/Response Schemas

Pydantic models for all request/response payloads, providing:
- Input validation with field constraints (min/max length, regex patterns)
- Serialization to JSON for HTTP responses
- Immutability (frozen=True) to prevent accidental mutation
- Comprehensive error details on validation failure
"""

from typing import Optional, List, Literal
from datetime import datetime
import uuid

from pydantic import BaseModel, Field


# ============================================================================
# Request Schemas
# ============================================================================


class ValidateRequest(BaseModel):
    """
    Single validation request.
    
    Maps to POST /validate endpoint.
    """
    
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="User query or instruction (required)"
    )
    
    output: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="LLM-generated response to validate (required)"
    )
    
    context: Optional[str] = Field(
        None,
        max_length=50000,
        description="Reference context for fact-checking (optional)"
    )
    
    policy: str = Field(
        default="default",
        min_length=1,
        max_length=100,
        pattern=r"^[a-zA-Z0-9_\-]+$",
        description="Policy name (alphanumeric, underscore, hyphen; default: 'default')"
    )
    
    domain: Optional[str] = Field(
        default="general",
        max_length=100,
        pattern=r"^[a-zA-Z0-9_\-]+$",
        description="Domain/category for context (optional, default: 'general')"
    )
    
    use_refinement: bool = Field(
        default=False,
        description="Return suggested fixes and preprocessing metadata (default: False)"
    )
    
    model_config = {"frozen": True}


class BatchValidateRequestItem(BaseModel):
    """
    Single item in a batch validation request.
    
    Same fields as ValidateRequest but all optional ID for tracking.
    """
    
    id: Optional[str] = Field(
        default_factory=lambda: f"req_{uuid.uuid4().hex[:12]}",
        max_length=100,
        description="Request identifier for tracking (optional, auto-generated if omitted)"
    )
    
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="User query or instruction (required)"
    )
    
    output: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="LLM-generated response to validate (required)"
    )
    
    context: Optional[str] = Field(
        None,
        max_length=50000,
        description="Reference context for fact-checking (optional)"
    )
    
    policy: str = Field(
        default="default",
        min_length=1,
        max_length=100,
        pattern=r"^[a-zA-Z0-9_\-]+$",
        description="Policy name (alphanumeric, underscore, hyphen)"
    )
    
    domain: Optional[str] = Field(
        default="general",
        max_length=100,
        pattern=r"^[a-zA-Z0-9_\-]+$",
        description="Domain/category for context (optional)"
    )
    
    use_refinement: bool = Field(
        default=False,
        description="Return suggested fixes and preprocessing metadata"
    )
    
    model_config = {"frozen": True}


class BatchValidateRequest(BaseModel):
    """
    Batch validation request.
    
    Maps to POST /validate/batch endpoint.
    """
    
    requests: List[BatchValidateRequestItem] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Array of validation requests (1-100 items)"
    )
    
    mode: Literal["parallel", "sequential"] = Field(
        default="parallel",
        description="Execution mode: 'parallel' or 'sequential' (default: 'parallel')"
    )
    
    timeout_per_request_ms: int = Field(
        default=30000,
        ge=1000,
        le=120000,
        description="Timeout per request in milliseconds (1s-2m, default: 30s)"
    )
    
    model_config = {"frozen": True}


# ============================================================================
# Response Schemas
# ============================================================================


class ValidationTierResult(BaseModel):
    """
    Single validator/tier result.
    
    Returned as part of tier_results in ValidationResponse.
    """
    
    validator_name: str = Field(
        ...,
        description="Name of the validator (e.g., 'heuristics', 'embedding', 'hhem')"
    )
    
    score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Faithfulness score [0.0=hallucinated, 1.0=faithful]"
    )
    
    passed: bool = Field(
        ...,
        description="Whether the validation passed the configured threshold"
    )
    
    evidence: str = Field(
        ...,
        description="Human-readable explanation of the validation result"
    )
    
    latency_ms: float = Field(
        ...,
        ge=0.0,
        description="Time taken for this validator in milliseconds"
    )
    
    model_config = {"frozen": True}


class PreprocessingMetadata(BaseModel):
    """
    Optional preprocessing metadata from prompt analysis.
    
    Included when use_refinement=True.
    """
    
    core_task: Optional[str] = Field(
        None,
        description="Extracted core task from prompt analysis"
    )
    
    entities: Optional[List[str]] = Field(
        None,
        description="Named entities extracted from prompt/output"
    )
    
    context_requirements: Optional[List[str]] = Field(
        None,
        description="Inferred context requirements based on task"
    )
    
    model_config = {"frozen": True}


class ValidationResponse(BaseModel):
    """
    Single validation response.
    
    Returned from POST /validate and in batch results.
    Maps to GuardDecision from SDK.
    """
    
    decision: Literal["allow", "block", "regenerate", "abstain"] = Field(
        ...,
        description="Action to take: allow (safe), block (hallucination), regenerate (fix & retry), abstain (uncertain)"
    )
    
    risk_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall risk score [0.0=safe, 1.0=maximum risk]"
    )
    
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence in decision based on validator agreement [0.0-1.0]"
    )
    
    evidence: str = Field(
        ...,
        description="Human-readable explanation of the decision"
    )
    
    output: Optional[str] = Field(
        None,
        description="The validated output (same as input unless modified)"
    )
    
    suggested_fix: Optional[str] = Field(
        None,
        description="Regeneration hint if decision='regenerate'"
    )
    
    latency_ms: float = Field(
        ...,
        ge=0.0,
        description="Total pipeline execution time in milliseconds"
    )
    
    policy_name: str = Field(
        ...,
        description="Name of the policy used for decision making"
    )
    
    tier_results: Optional[List[ValidationTierResult]] = Field(
        None,
        description="Individual validation results from each tier/validator"
    )
    
    preprocessing_metadata: Optional[PreprocessingMetadata] = Field(
        None,
        description="Preprocessing results (prompt analysis, context requirements)"
    )
    
    model_config = {"frozen": True}


class BatchValidationResultItem(BaseModel):
    """
    Single result item in batch response.
    
    Wraps ValidationResponse with request ID and optional error.
    """
    
    id: str = Field(
        ...,
        description="Request identifier (matches input request.id)"
    )
    
    decision: Optional[Literal["allow", "block", "regenerate", "abstain"]] = Field(
        None,
        description="Validation decision (None if error occurred)"
    )
    
    risk_score: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Risk score (None if error occurred)"
    )
    
    confidence: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Confidence in decision (None if error occurred)"
    )
    
    evidence: Optional[str] = Field(
        None,
        description="Evidence/explanation (None if error occurred)"
    )
    
    latency_ms: Optional[float] = Field(
        None,
        ge=0.0,
        description="Validation latency (None if error occurred)"
    )
    
    error: Optional[str] = Field(
        None,
        description="Error message if validation failed"
    )
    
    model_config = {"frozen": True}


class BatchValidationResponse(BaseModel):
    """
    Batch validation response.
    
    Returned from POST /validate/batch endpoint.
    """
    
    batch_id: str = Field(
        ...,
        description="UUID for tracking this batch"
    )
    
    total_requests: int = Field(
        ...,
        ge=1,
        description="Total number of requests in batch"
    )
    
    successful_validations: int = Field(
        ...,
        ge=0,
        description="Number of successful validations"
    )
    
    failed_validations: int = Field(
        ...,
        ge=0,
        description="Number of failed validations"
    )
    
    results: List[BatchValidationResultItem] = Field(
        ...,
        description="Array of per-request results"
    )
    
    batch_latency_ms: float = Field(
        ...,
        ge=0.0,
        description="Total batch execution time in milliseconds"
    )
    
    errors: Optional[List[str]] = Field(
        None,
        description="Batch-level errors (not per-request)"
    )
    
    model_config = {"frozen": True}


class HealthCheckResponse(BaseModel):
    """
    Health check response.
    
    Returned from GET /health endpoint.
    """
    
    status: Literal["healthy", "degraded", "unhealthy"] = Field(
        ...,
        description="Overall system status: healthy, degraded, or unhealthy"
    )
    
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp of health check"
    )
    
    validators: dict = Field(
        ...,
        description="Validator availability status with latency info"
    )
    
    uptime_seconds: int = Field(
        ...,
        ge=0,
        description="Server uptime in seconds"
    )
    
    requests_processed: int = Field(
        ...,
        ge=0,
        description="Total requests processed since startup"
    )
    
    model_config = {"frozen": True}


class VersionResponse(BaseModel):
    """
    Version information response.
    
    Returned from GET /version endpoint.
    """
    
    api_version: str = Field(
        ...,
        description="REST API version (e.g., '1.0.0')"
    )
    
    sdk_version: str = Field(
        ...,
        description="HallucinationGuard SDK version"
    )
    
    python_version: str = Field(
        ...,
        description="Python runtime version"
    )
    
    transformers_version: str = Field(
        ...,
        description="transformers library version"
    )
    
    torch_version: str = Field(
        ...,
        description="torch library version"
    )
    
    policy_schema_version: str = Field(
        ...,
        description="Policy YAML schema version"
    )
    
    model_config = {"frozen": True}


class PolicyMetadata(BaseModel):
    """
    Metadata for a single policy.
    
    Used in PoliciesResponse.
    """
    
    name: str = Field(
        ...,
        description="Policy identifier"
    )
    
    description: str = Field(
        ...,
        description="Human-readable policy description"
    )
    
    risk_threshold: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Maximum acceptable risk score [0.0-1.0]"
    )
    
    validators_enabled: List[str] = Field(
        ...,
        description="List of enabled validators in this policy"
    )
    
    latency_budget_ms: int = Field(
        ...,
        ge=0,
        description="Maximum total pipeline latency in milliseconds"
    )
    
    model_config = {"frozen": True}


class PoliciesResponse(BaseModel):
    """
    List of available policies response.
    
    Returned from GET /config/policies endpoint.
    """
    
    policies: List[PolicyMetadata] = Field(
        ...,
        description="Array of available policy configurations"
    )
    
    model_config = {"frozen": True}


# ============================================================================
# Error Schemas
# ============================================================================


class ErrorDetails(BaseModel):
    """
    Detailed error information.
    
    Provides context about validation failures or request errors.
    """
    
    field: Optional[str] = Field(
        None,
        description="Field name that failed validation (for VALIDATION_ERROR)"
    )
    
    constraint: Optional[str] = Field(
        None,
        description="Constraint that failed (e.g., 'required', 'min_length', 'regex')"
    )
    
    provided_type: Optional[str] = Field(
        None,
        description="Type of value provided (for type mismatches)"
    )
    
    expected_type: Optional[str] = Field(
        None,
        description="Expected type (for type mismatches)"
    )
    
    message: Optional[str] = Field(
        None,
        description="Additional error detail message"
    )
    
    model_config = {"frozen": True}


class ErrorResponse(BaseModel):
    """
    Standard error response format.
    
    Returned by all endpoints on error.
    """
    
    status_code: int = Field(
        ...,
        ge=400,
        le=599,
        description="HTTP status code (4xx or 5xx)"
    )
    
    code: str = Field(
        ...,
        pattern=r"^[A-Z_]+$",
        description="Machine-readable error code (e.g., 'INVALID_INPUT', 'AUTH_FAILED')"
    )
    
    message: str = Field(
        ...,
        description="Human-readable error message"
    )
    
    details: Optional[ErrorDetails] = Field(
        None,
        description="Detailed error information (optional)"
    )
    
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp of error"
    )
    
    request_id: str = Field(
        ...,
        description="Unique request identifier for debugging/support"
    )
    
    model_config = {"frozen": True}
