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
else:
    Langfuse = None
    try:
        from langfuse import Langfuse  # noqa: F811
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

    model_config = {"frozen": True}

    @classmethod
    def from_decision(
        cls,
        decision: dict[str, Any],
        prompt: str,
        output: str,
        context: Optional[str] = None,
        domain: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> "GuardTrace":
        """Create a GuardTrace from a validation decision.

        Maps decision data to trace format for observability. Designed to work
        with GuardDecision once that schema is implemented; currently accepts
        a dict with decision, risk_score, evidence, and validation_results.

        Args:
            decision: Decision dict with keys: id, decision, risk_score, evidence,
                      validation_results (list of validator results)
            prompt: User prompt that triggered validation
            output: Model-generated output being validated
            context: Optional reference context used for validation
            domain: Optional domain metadata (e.g., "healthcare", "finance")
            tags: Optional tags for categorization

        Returns:
            GuardTrace instance with all decision metadata

        Note:
            Once GuardDecision schema is implemented in decision.py, this method
            will be updated to accept GuardDecision objects directly.
        """
        input_data = {
            "prompt": prompt,
            "output": output,
            "context": context,
            "domain": domain,
        }

        metadata = {
            "decision": decision.get("decision", "unknown"),
            "risk_score": decision.get("risk_score", 0.5),
            "evidence": decision.get("evidence", ""),
            "validation_results": decision.get("validation_results", []),
        }

        return cls(
            id=decision.get("id", str(uuid4())),
            timestamp=decision.get("timestamp", datetime.now(timezone.utc).isoformat()),
            input=input_data,
            output=output,
            metadata=metadata,
            tags=tags or [],
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
