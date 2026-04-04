"""
Policy configuration schemas.

Defines Pydantic models for validator configuration, mitigation strategies,
and complete policy definitions.
"""

from typing import Literal
from pydantic import BaseModel, Field


class ValidatorConfig(BaseModel):
    """Configuration for a single validator in the pipeline."""

    name: str = Field(..., description="Validator identifier (e.g., 'heuristics', 'embedding', 'hhem')")
    enabled: bool = Field(default=True, description="Whether this validator is active")
    weight: float = Field(..., ge=0.0, le=1.0, description="Weight in score aggregation (0.0-1.0)")
    threshold: float = Field(..., ge=0.0, le=1.0, description="Minimum score to pass (0.0-1.0)")
    timeout_ms: int = Field(..., gt=0, description="Maximum execution time in milliseconds")

    class Config:
        frozen = True


class MitigationConfig(BaseModel):
    """Configuration for mitigation strategies when validation fails or degrades."""

    on_block: Literal["block", "regenerate", "allow", "abstain"] = Field(
        default="block",
        description="Action when validators signal hallucination",
    )
    on_timeout: Literal["block", "regenerate", "allow", "abstain"] = Field(
        default="allow",
        description="Action when validators exceed latency budget",
    )
    on_error: Literal["block", "regenerate", "allow", "abstain"] = Field(
        default="abstain",
        description="Action when validators crash or error",
    )

    class Config:
        frozen = True


class ArmorIQConfig(BaseModel):
    """Configuration for the ArmorIQ intent enforcement layer.

    ArmorIQ operates as an optional second layer AFTER text validation passes.
    It checks that proposed agent actions align with the user's declared task
    scope, blocking dangerous or out-of-scope actions before execution.

    Modes:
        stub:    Log intent checks, always allow (safe offline default).
        enforce: Block misaligned actions using the configured client.

    Example YAML::

        armoriq:
          enabled: true
          mode: "enforce"
          on_violation: "block"
    """

    enabled: bool = Field(
        default=False,
        description="Whether to activate ArmorIQ intent enforcement",
    )
    mode: Literal["stub", "enforce"] = Field(
        default="stub",
        description=(
            "'stub' = log only, never block (safe default). "
            "'enforce' = actively block misaligned actions."
        ),
    )
    on_violation: Literal["block", "warn", "log"] = Field(
        default="block",
        description="Action taken when an intent violation is detected",
    )

    class Config:
        frozen = True


class PolicyConfig(BaseModel):
    """Complete policy definition for the HallucinationGuard pipeline."""

    name: str = Field(..., description="Policy identifier")
    description: str = Field(default="", description="Human-readable policy description")
    latency_budget_ms: int = Field(..., gt=0, description="Maximum total pipeline latency in milliseconds")
    risk_threshold: float = Field(..., ge=0.0, le=1.0, description="Maximum acceptable risk score (0.0-1.0)")

    # Prompt validator configuration (Tier 0.5)
    enable_prompt_validators: bool = Field(
        default=True,
        description="Whether to enable prompt security validators (Tier 0.5)",
    )
    prompt_injection_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Maximum acceptable prompt injection risk (0.0-1.0). <30% typical.",
    )

    validators: list[ValidatorConfig] = Field(..., min_length=1, description="List of validator configurations")
    mitigation: MitigationConfig = Field(default_factory=MitigationConfig, description="Mitigation strategies")

    # ArmorIQ intent enforcement (optional, disabled by default)
    armoriq: ArmorIQConfig = Field(
        default_factory=ArmorIQConfig,
        description="ArmorIQ intent enforcement configuration (optional, off by default)",
    )

    class Config:
        frozen = True
