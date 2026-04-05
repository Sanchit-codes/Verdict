"""Middleware for request/response handling, error handling, and logging."""

import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from functools import wraps
from typing import Any

from flask import Flask, jsonify, request
from pydantic import ValidationError

from .config import Config
from .schemas import ErrorResponse

logger = logging.getLogger(__name__)


def add_request_id(request_obj: Any) -> str:
    """Add unique request ID for tracing."""
    request_id = str(uuid.uuid4())[:8]
    request_obj.request_id = request_id
    return request_id


def log_request(f: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to log incoming requests with ID and latency."""

    @wraps(f)
    def decorated_function(*args: Any, **kwargs: Any) -> Any:
        request_id = add_request_id(request)
        start_time = datetime.utcnow()

        # Log request
        logger.info(
            f"[{request_id}] {request.method} {request.path} " f"| client={request.remote_addr}"
        )

        try:
            result = f(*args, **kwargs)
            elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000

            # Log response
            status_code = result[1] if isinstance(result, tuple) else 200
            logger.info(
                f"[{request_id}] {request.method} {request.path} "
                f"| status={status_code} | latency={elapsed:.1f}ms"
            )

            return result
        except Exception as e:
            elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.error(
                f"[{request_id}] {request.method} {request.path} | error={str(e)} "
                f"| latency={elapsed:.1f}ms",
                exc_info=True,
            )
            raise

    return decorated_function


def setup_error_handlers(app: Flask) -> None:
    """Register global error handlers for the Flask app."""

    @app.errorhandler(ValidationError)  # type: ignore
    def handle_validation_error(e: ValidationError) -> Any:
        """Handle Pydantic validation errors."""
        # Extract first error for clarity
        errors = e.errors()
        first_error = errors[0] if errors else {}
        field = ".".join(str(x) for x in first_error.get("loc", []))
        msg = first_error.get("msg", "Validation failed")

        error_response = ErrorResponse(
            error=f"Invalid request: {msg}",
            code="VALIDATION_ERROR",
            details={"field": field, "reason": msg, "all_errors": len(errors)},
        )

        logger.warning(f"Validation error: {field} - {msg}")
        return jsonify(error_response.model_dump()), 422

    @app.errorhandler(400)  # type: ignore
    def handle_bad_request(e: Any) -> Any:
        """Handle bad request errors."""
        error_response = ErrorResponse(
            error="Bad request",
            code="BAD_REQUEST",
            details={"message": str(e)},
        )
        return jsonify(error_response.model_dump()), 400

    @app.errorhandler(404)  # type: ignore
    def handle_not_found(e: Any) -> Any:
        """Handle 404 errors."""
        error_response = ErrorResponse(
            error="Endpoint not found",
            code="NOT_FOUND",
            details={"path": request.path, "method": request.method},
        )
        return jsonify(error_response.model_dump()), 404

    @app.errorhandler(500)  # type: ignore
    def handle_server_error(e: Any) -> Any:
        """Handle server errors."""
        logger.error(f"Server error: {str(e)}", exc_info=True)
        error_response = ErrorResponse(
            error="Internal server error",
            code="SERVER_ERROR",
            details={"message": "An unexpected error occurred"},
        )
        return jsonify(error_response.model_dump()), 500


def setup_cors(app: Flask) -> None:
    """Setup CORS headers for development based on configuration."""

    @app.after_request  # type: ignore
    def after_request(response: Any) -> Any:
        """Add CORS headers to all responses."""
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "*"
        return response

    @app.route("/<path:path>", methods=["OPTIONS"])  # type: ignore
    def handle_options(path: str) -> Any:
        """Handle preflight requests."""
        return "", 204


def setup_logging(log_level: str = "INFO") -> None:
    """Setup structured logging for the application."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Suppress verbose werkzeug logs
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
