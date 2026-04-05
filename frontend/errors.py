#!/usr/bin/env python3
"""
Flask Error Handlers

Provides error handling for the REST API, converting exceptions to
standard error responses with proper HTTP status codes and error codes.

Error response format:
{
    "status_code": 400,
    "code": "INVALID_INPUT",
    "message": "Human-readable message",
    "details": {...},
    "timestamp": "2025-01-10T12:00:00Z",
    "request_id": "req_abc123"
}
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from flask import Flask, jsonify, request
from pydantic import ValidationError

from hallucination_guard.core.exceptions import (
    HallucinationGuardError,
    PolicyLoadError,
    ValidationTimeoutError,
    IntentViolationError,
    HallucinationBlockedError,
)

from frontend.schemas import ErrorResponse, ErrorDetails


logger = logging.getLogger(__name__)


# ============================================================================
# Utility Functions
# ============================================================================


def generate_request_id() -> str:
    """Generate a unique request ID for error tracking."""
    return f"req_{uuid.uuid4().hex[:12]}"


def get_current_timestamp() -> str:
    """Get current timestamp in ISO 8601 format."""
    return datetime.utcnow().isoformat() + "Z"


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Optional[ErrorDetails] = None,
    request_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], int]:
    """
    Create a standard error response.
    
    Args:
        status_code: HTTP status code (400-599)
        code: Machine-readable error code (e.g., 'INVALID_INPUT')
        message: Human-readable error message
        details: Optional ErrorDetails with additional context
        request_id: Optional custom request ID (auto-generated if omitted)
    
    Returns:
        Tuple of (response_dict, status_code) for Flask
    """
    request_id = request_id or generate_request_id()
    
    response = {
        "status_code": status_code,
        "code": code,
        "message": message,
        "details": details.model_dump(exclude_none=True) if details else None,
        "timestamp": get_current_timestamp(),
        "request_id": request_id,
    }
    
    # Remove None details to keep response clean
    if response["details"] is None:
        del response["details"]
    
    return response, status_code


def validation_error_response(
    pydantic_error: ValidationError,
    request_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], int]:
    """
    Convert Pydantic ValidationError to standard error response.
    
    Args:
        pydantic_error: Pydantic ValidationError from request validation
        request_id: Optional custom request ID
    
    Returns:
        Tuple of (response_dict, 422) for Flask
    """
    request_id = request_id or generate_request_id()
    
    # Extract first error for details
    errors = pydantic_error.errors()
    first_error = errors[0] if errors else {}
    
    # Build details from first error
    details_dict = {}
    if "loc" in first_error and first_error["loc"]:
        details_dict["field"] = str(first_error["loc"][0])
    
    error_type = first_error.get("type", "value_error")
    if error_type == "missing":
        details_dict["constraint"] = "required"
    elif error_type == "string_too_short":
        details_dict["constraint"] = "min_length"
    elif error_type == "string_too_long":
        details_dict["constraint"] = "max_length"
    elif error_type == "string_pattern_mismatch":
        details_dict["constraint"] = "regex"
    elif error_type == "type_error":
        details_dict["constraint"] = "type"
    else:
        details_dict["constraint"] = error_type
    
    if "input" in first_error:
        details_dict["provided_type"] = type(first_error["input"]).__name__
    
    if "msg" in first_error:
        details_dict["message"] = first_error["msg"]
    
    details = ErrorDetails(**details_dict)
    
    return error_response(
        status_code=422,
        code="VALIDATION_ERROR",
        message="Request validation failed",
        details=details,
        request_id=request_id,
    )


# ============================================================================
# Flask Error Handlers
# ============================================================================


def register_error_handlers(app: Flask) -> None:
    """
    Register all error handlers with Flask app.
    
    Usage:
        app = Flask(__name__)
        register_error_handlers(app)
    """
    
    @app.errorhandler(ValidationError)
    def handle_pydantic_validation_error(error: ValidationError):
        """Handle Pydantic validation errors (422)."""
        response, status_code = validation_error_response(error)
        return jsonify(response), status_code
    
    @app.errorhandler(PolicyLoadError)
    def handle_policy_load_error(error: PolicyLoadError):
        """Handle policy loading errors (400)."""
        details = ErrorDetails(message=error.reason or str(error))
        response, status_code = error_response(
            status_code=400,
            code="INVALID_INPUT",
            message=f"Failed to load policy '{error.policy_name}': {error.reason}",
            details=details,
        )
        logger.warning(f"Policy load error: {error.policy_name} - {error.reason}")
        return jsonify(response), status_code
    
    @app.errorhandler(ValidationTimeoutError)
    def handle_validation_timeout_error(error: ValidationTimeoutError):
        """Handle validation timeout errors (503)."""
        details = ErrorDetails(
            message=f"Validation exceeded latency budget: {error.latency_ms:.1f}ms > {error.budget_ms}ms"
        )
        response, status_code = error_response(
            status_code=503,
            code="SERVICE_DEGRADED",
            message="Validation timeout: Service in graceful degradation mode",
            details=details,
        )
        logger.warning(f"Validation timeout: {error.latency_ms:.1f}ms > {error.budget_ms}ms")
        return jsonify(response), status_code
    
    @app.errorhandler(IntentViolationError)
    def handle_intent_violation_error(error: IntentViolationError):
        """Handle intent violation errors (400)."""
        details = ErrorDetails(
            message=f"Task '{error.user_task}' does not authorize action: {error.reason}"
        )
        response, status_code = error_response(
            status_code=400,
            code="INVALID_INPUT",
            message="Action violates declared task scope",
            details=details,
        )
        logger.warning(f"Intent violation: {error.user_task} - {error.action_plan}")
        return jsonify(response), status_code
    
    @app.errorhandler(HallucinationBlockedError)
    def handle_hallucination_blocked_error(error: HallucinationBlockedError):
        """Handle hallucination blocked errors (400)."""
        details = ErrorDetails(
            message=f"Output blocked by validation pipeline (risk={error.risk_score:.2f})"
        )
        response, status_code = error_response(
            status_code=400,
            code="INVALID_INPUT",
            message=f"Output validation failed: {error.evidence}",
            details=details,
        )
        logger.info(f"Hallucination blocked: risk={error.risk_score:.2f}")
        return jsonify(response), status_code
    
    @app.errorhandler(HallucinationGuardError)
    def handle_hallucination_guard_error(error: HallucinationGuardError):
        """Handle generic HallucinationGuard errors (400)."""
        details = ErrorDetails(message=str(error))
        response, status_code = error_response(
            status_code=400,
            code="INVALID_INPUT",
            message=f"SDK error: {str(error)}",
            details=details,
        )
        logger.error(f"HallucinationGuard error: {type(error).__name__} - {error}")
        return jsonify(response), status_code
    
    @app.errorhandler(400)
    def handle_bad_request(error):
        """Handle HTTP 400 Bad Request (e.g., missing required JSON fields)."""
        response, status_code = error_response(
            status_code=400,
            code="INVALID_INPUT",
            message="Bad request: " + (str(error) if error else "Invalid request"),
        )
        return jsonify(response), status_code
    
    @app.errorhandler(401)
    def handle_unauthorized(error):
        """Handle HTTP 401 Unauthorized (authentication failures)."""
        response, status_code = error_response(
            status_code=401,
            code="AUTH_FAILED",
            message="Unauthorized: Invalid or missing API key",
        )
        return jsonify(response), status_code
    
    @app.errorhandler(404)
    def handle_not_found(error):
        """Handle HTTP 404 Not Found (endpoint not found)."""
        response, status_code = error_response(
            status_code=404,
            code="NOT_FOUND",
            message="Endpoint not found",
        )
        return jsonify(response), status_code
    
    @app.errorhandler(429)
    def handle_rate_limited(error):
        """Handle HTTP 429 Rate Limited."""
        response, status_code = error_response(
            status_code=429,
            code="RATE_LIMITED",
            message="Rate limit exceeded",
        )
        return jsonify(response), status_code
    
    @app.errorhandler(500)
    def handle_internal_server_error(error):
        """Handle HTTP 500 Internal Server Error (unhandled exceptions)."""
        request_id = generate_request_id()
        logger.error(
            f"Unhandled exception: {type(error).__name__} - {error}",
            exc_info=True,
            extra={"request_id": request_id},
        )
        response, status_code = error_response(
            status_code=500,
            code="INTERNAL_ERROR",
            message="Internal server error",
            request_id=request_id,
        )
        return jsonify(response), status_code
    
    @app.errorhandler(503)
    def handle_service_unavailable(error):
        """Handle HTTP 503 Service Unavailable."""
        response, status_code = error_response(
            status_code=503,
            code="SERVICE_DEGRADED",
            message="Service temporarily unavailable",
        )
        return jsonify(response), status_code
    
    @app.errorhandler(Exception)
    def handle_generic_exception(error: Exception):
        """Catch-all handler for any unhandled exception."""
        request_id = generate_request_id()
        error_type = type(error).__name__
        
        logger.error(
            f"Unhandled exception: {error_type} - {error}",
            exc_info=True,
            extra={"request_id": request_id},
        )
        
        # Default to 500 Internal Server Error
        response, status_code = error_response(
            status_code=500,
            code="INTERNAL_ERROR",
            message=f"Internal server error ({error_type})",
            request_id=request_id,
        )
        return jsonify(response), status_code


# ============================================================================
# Middleware Utilities
# ============================================================================


def wrap_endpoint(f):
    """
    Decorator to wrap endpoint with JSON error handling.
    
    Converts response to JSON if not already, catches exceptions,
    and ensures proper error response format.
    
    Usage:
        @app.route('/validate', methods=['POST'])
        @wrap_endpoint
        def validate():
            # endpoint code
            return result_dict
    """
    from functools import wraps
    
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            result = f(*args, **kwargs)
            
            # If result is dict, convert to JSON response
            if isinstance(result, dict):
                return jsonify(result)
            
            return result
        
        except ValidationError as e:
            response, status_code = validation_error_response(e)
            return jsonify(response), status_code
        
        except Exception as e:
            # Let Flask's error handlers take over
            raise
    
    return decorated


# ============================================================================
# Response Validation (Optional, for testing)
# ============================================================================


def validate_error_response(response_dict: Dict[str, Any]) -> bool:
    """
    Validate that an error response matches ErrorResponse schema.
    
    Useful for testing and debugging.
    
    Args:
        response_dict: Error response dictionary
    
    Returns:
        True if valid, raises ValidationError if not
    """
    ErrorResponse(**response_dict)
    return True
