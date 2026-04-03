"""Trace logging for HallucinationGuard validation decisions.

This module provides observability for debugging and monitoring validation
decisions. Traces are persisted to JSONL files and optionally exported to
Langfuse cloud for visualization and analysis.

Trace Features:
- Langfuse-compatible schema for cloud export
- JSONL persistence to local disk with automatic directory creation
- Graceful degradation on export failures (never crashes validation)
- Support for custom metadata and tags
- Immutable schemas (frozen=True) for consistency

Example:
    >>> from hallucination_guard.core.trace import GuardTrace, export_trace
    >>> trace = GuardTrace.from_decision({
    ...     "id": "abc123",
    ...     "decision": "allow",
    ...     "risk_score": 0.15,
    ...     "evidence": "High context overlap",
    ... }, prompt="What is AI?", output="AI is...")
    >>> export_trace(trace)  # Writes to JSONL + optionally Langfuse
"""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Try to import Langfuse for optional cloud export
if TYPE_CHECKING:
    from langfuse import Langfuse
    from hallucination_guard.core.decision import GuardDecision
else:
    Langfuse = None
    GuardDecision = None
    try:
        from langfuse import Langfuse  # noqa: F811
    except ImportError:
        pass
    try:
        from hallucination_guard.core.decision import GuardDecision  # noqa: F811
    except ImportError:
        pass


class GuardTrace(BaseModel):
    """Langfuse-compatible trace schema for validation decisions.

    This model records all metadata from a validation run for observability.
    Frozen=True ensures immutability and consistency across the pipeline.

    Attributes:
        id: Unique trace identifier (UUID v4)
        timestamp: ISO 8601 timestamp when validation occurred
        name: Fixed value "hallucination_guard_validation" for Langfuse compatibility
        input: Validation input (prompt, output, context)
        output: Model-generated output being validated
        metadata: Additional context (decision, risk_score, evidence, latency_ms, etc.)
        tags: List of tags for categorization (e.g., ["rag", "healthcare"])
        prompt_injection_risk: Pre-computed prompt injection risk in [0.0, 1.0]
        prompt_security_metadata: Additional prompt security analysis metadata
        structured_prompt: Extracted structured prompt data from security metadata
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    name: str = "hallucination_guard_validation"
    input: dict[str, Any] = Field(default_factory=dict)
    output: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    prompt_injection_risk: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Pre-computed prompt injection risk from security analysis"
    )
    prompt_security_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional prompt security analysis metadata"
    )
    structured_prompt: Optional[dict[str, Any]] = Field(
        default=None,
        description="Extracted structured prompt data from security metadata"
    )

    model_config = {"frozen": True}

    @classmethod
    def from_decision(
        cls,
        decision: "GuardDecision | dict[str, Any]",
        prompt: str,
        output: str,
        context: Optional[str] = None,
        domain: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> "GuardTrace":
        """Create a GuardTrace from a validation decision.

        Maps decision data to trace format for observability, including prompt
        security analysis metadata. Supports both GuardDecision objects and
        legacy dicts for backward compatibility.

        Args:
            decision: GuardDecision object or dict with decision, risk_score, evidence,
                      validation_results, and prompt security metadata
            prompt: User prompt that triggered validation
            output: Model-generated output being validated
            context: Optional reference context used for validation
            domain: Optional domain metadata (e.g., "healthcare", "finance")
            tags: Optional tags for categorization

        Returns:
            GuardTrace instance with all decision metadata including prompt security data
        """
        input_data = {
            "prompt": prompt,
            "output": output,
            "context": context,
            "domain": domain,
        }

        # Support both GuardDecision objects and dicts for backward compatibility
        is_guard_decision = hasattr(decision, "decision") and hasattr(decision, "risk_score")
        
        if is_guard_decision:
            # Handle GuardDecision object
            metadata = {
                "decision": decision.decision,  # type: ignore[attr-defined]
                "risk_score": decision.risk_score,  # type: ignore[attr-defined]
                "evidence": decision.evidence,  # type: ignore[attr-defined]
                "validation_results": [r.model_dump() for r in decision.validator_results],  # type: ignore[attr-defined]
                "policy_name": decision.policy_name,  # type: ignore[attr-defined]
                "latency_ms": decision.latency_ms,  # type: ignore[attr-defined]
                "confidence": decision.confidence,  # type: ignore[attr-defined]
            }
            
            if decision.suggested_fix:  # type: ignore[attr-defined]
                metadata["suggested_fix"] = decision.suggested_fix  # type: ignore[attr-defined]

            # Extract structured_prompt from prompt_security_metadata if available
            structured_prompt: Optional[dict[str, Any]] = None
            if decision.prompt_security_metadata:  # type: ignore[attr-defined]
                sp = decision.prompt_security_metadata.get("structured_prompt")  # type: ignore[attr-defined]
                if isinstance(sp, dict):
                    structured_prompt = sp

            return cls(
                id=str(uuid4()),  # Generate new trace ID
                timestamp=datetime.now(timezone.utc).isoformat(),
                input=input_data,
                output=output,
                metadata=metadata,
                tags=tags or [],
                prompt_injection_risk=decision.prompt_injection_risk,  # type: ignore[attr-defined]
                prompt_security_metadata=decision.prompt_security_metadata,  # type: ignore[attr-defined]
                structured_prompt=structured_prompt,
            )
        else:
            # Handle legacy dict format for backward compatibility
            metadata = {
                "decision": decision.get("decision", "unknown"),
                "risk_score": decision.get("risk_score", 0.5),
                "evidence": decision.get("evidence", ""),
                "validation_results": decision.get("validation_results", []),
            }
            
            # Add optional fields from dict if present
            if "policy_name" in decision:
                metadata["policy_name"] = decision["policy_name"]
            if "latency_ms" in decision:
                metadata["latency_ms"] = decision["latency_ms"]
            if "confidence" in decision:
                metadata["confidence"] = decision["confidence"]
            if "suggested_fix" in decision:
                metadata["suggested_fix"] = decision["suggested_fix"]

            # Extract structured_prompt if present in dict
            structured_prompt = None
            prompt_security_metadata = decision.get("prompt_security_metadata", {})
            if isinstance(prompt_security_metadata, dict):
                sp = prompt_security_metadata.get("structured_prompt")
                if isinstance(sp, dict):
                    structured_prompt = sp

            return cls(
                id=decision.get("id", str(uuid4())),
                timestamp=decision.get("timestamp", datetime.now(timezone.utc).isoformat()),
                input=input_data,
                output=output,
                metadata=metadata,
                tags=tags or [],
                prompt_injection_risk=decision.get("prompt_injection_risk", 0.0),
                prompt_security_metadata=prompt_security_metadata,
                structured_prompt=structured_prompt,
            )


def export_trace(trace: GuardTrace, trace_dir: Optional[str] = None) -> None:
    """Export a trace to JSONL file and optionally to Langfuse.

    Writes one JSON line per trace to a dated JSONL file. Langfuse export is
    attempted if credentials are configured, but failures are logged as warnings
    and never crash the validation pipeline.

    Args:
        trace: GuardTrace instance to export
        trace_dir: Directory for JSONL files. Defaults to $HG_TRACE_DIR or
                   ~/.hallucination_guard/traces/

    Note:
        - Always exports to JSONL (file-based observability)
        - Optionally exports to Langfuse if credentials are set
        - All errors are caught and logged; never raises exceptions
        - Creates trace_dir if it doesn't exist
    """
    if trace_dir is None:
        trace_dir = os.getenv(
            "HG_TRACE_DIR",
            str(Path.home() / ".hallucination_guard" / "traces"),
        )

    # Ensure directory exists
    try:
        Path(trace_dir).mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"Failed to create trace directory {trace_dir}: {e}")
        return

    # Write to JSONL file
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        jsonl_path = Path(trace_dir) / f"{today}.jsonl"

        with open(jsonl_path, "a", encoding="utf-8") as f:
            f.write(trace.model_dump_json() + "\n")

        logger.debug(f"Trace exported to {jsonl_path}")
    except Exception as e:
        logger.warning(f"Failed to export trace to JSONL: {e}")

    # Attempt Langfuse export (optional, graceful degradation)
    _export_to_langfuse(trace)


def _export_to_langfuse(trace: GuardTrace) -> None:
    """Export trace to Langfuse cloud (optional, graceful degradation).

    Attempts to export if credentials are configured. Handles all errors
    gracefully and logs warnings instead of raising exceptions.

    Args:
        trace: GuardTrace instance to export

    Note:
        - Only exports if LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set
        - Handles ImportError if langfuse is not installed (observability extra)
        - Handles API errors and invalid credentials gracefully
        - Never crashes validation pipeline
    """
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")

    if not public_key or not secret_key:
        # Credentials not configured - skip Langfuse export
        logger.debug("Langfuse credentials not configured, skipping cloud export")
        return

    # Check if langfuse is available (imported at module level)
    if Langfuse is None:
        logger.warning(
            "langfuse not installed. Install with: pip install langfuse"
        )
        return

    try:
        # Initialize client
        client = Langfuse(public_key=public_key, secret_key=secret_key)

        # Convert trace to Langfuse-compatible format
        # Langfuse expects: name, input, output, metadata, tags, timestamp
        client.trace(
            name=trace.name,
            input=trace.input,
            output=trace.output,
            metadata=trace.metadata,
            tags=trace.tags,
            timestamp=trace.timestamp,
            trace_id=trace.id,
        )

        logger.debug(f"Trace {trace.id} exported to Langfuse")

    except Exception as e:
        logger.warning(f"Failed to export trace to Langfuse: {e}")
