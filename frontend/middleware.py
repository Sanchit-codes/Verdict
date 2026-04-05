#!/usr/bin/env python3
"""
Flask Authentication & Logging Middleware

Provides:
- auth_required: Decorator to validate Bearer token from Authorization header
- RequestLogger: Middleware to log all requests/responses in structured JSON format
- Utility functions for key validation and masking
"""

import os
import time
import hashlib
import json
import logging
from functools import wraps
from typing import Optional, List, Callable
from datetime import datetime

from flask import Flask, request, jsonify, Response


# Configure structured logger for audit trail
def create_audit_logger(name: str = "audit") -> logging.Logger:
    """Create a structured JSON logger for audit trail."""
    logger = logging.getLogger(name)
    
    # Only configure if not already configured
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(handler)
    
    return logger


def hash_api_key(key: str) -> str:
    """
    Hash an API key for logging (never log full key).
    
    Returns first 3 chars + hash of full key for identification.
    Example: "sk-xxx_1a2b3c4d"
    """
    if not key or len(key) < 3:
        return "invalid"
    
    prefix = key[:3]
    full_hash = hashlib.sha256(key.encode()).hexdigest()[:8]
    return f"{prefix}...{full_hash}"


def mask_api_key(key: str) -> str:
    """
    Mask an API key for logging (show only first 3 and last 3 chars).
    
    Example: "sk-abc...xyz"
    """
    if not key or len(key) < 6:
        return "***"
    
    return f"{key[:3]}...{key[-3:]}"


def get_valid_api_keys() -> List[str]:
    """
    Load API keys from GUARDLY_API_KEYS environment variable.
    
    Format: "key1,key2,key3"
    Returns empty list if env var not set.
    """
    keys_str = os.getenv("GUARDLY_API_KEYS", "")
    if not keys_str:
        return []
    
    return [key.strip() for key in keys_str.split(",") if key.strip()]


def extract_bearer_token(authorization_header: Optional[str]) -> Optional[str]:
    """
    Extract Bearer token from Authorization header.
    
    Args:
        authorization_header: Value of Authorization header (e.g., "Bearer token123")
    
    Returns:
        Token string if valid Bearer format, None otherwise
    """
    if not authorization_header:
        return None
    
    parts = authorization_header.split()
    
    # Check for Bearer scheme
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    
    return parts[1]


def validate_api_key(api_key: str) -> bool:
    """
    Validate API key against list of valid keys.
    
    Args:
        api_key: API key to validate
    
    Returns:
        True if key is valid, False otherwise
    """
    valid_keys = get_valid_api_keys()
    
    # Allow requests if no valid keys configured (dev mode)
    if not valid_keys:
        return True
    
    return api_key in valid_keys


def auth_required(f: Callable) -> Callable:
    """
    Decorator to require Bearer token authentication on a Flask route.
    
    Validates Authorization header and returns 401 if invalid.
    
    Usage:
        @app.route('/protected', methods=['POST'])
        @auth_required
        def protected_endpoint():
            return jsonify({'success': True})
    
    Error Response (401):
        {
            "error": "Unauthorized",
            "code": "AUTH_FAILED",
            "message": "Invalid or missing API key"
        }
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        token = extract_bearer_token(auth_header)
        
        if not token:
            return jsonify({
                "error": "Unauthorized",
                "code": "AUTH_FAILED",
                "message": "Missing or malformed Authorization header. Use: Authorization: Bearer <key>"
            }), 401
        
        if not validate_api_key(token):
            logger = logging.getLogger(__name__)
            logger.warning(f"Invalid API key attempt: {hash_api_key(token)}")
            
            return jsonify({
                "error": "Unauthorized",
                "code": "AUTH_FAILED",
                "message": "Invalid API key"
            }), 401
        
        # Attach the validated key to request context for logging
        request.api_key = token
        
        return f(*args, **kwargs)
    
    return decorated_function


class RequestLogger:
    """
    WSGI middleware to log all requests and responses in structured JSON format.
    
    Logs:
    - method: HTTP method
    - path: Request path
    - status_code: HTTP status code
    - latency_ms: Request latency in milliseconds
    - timestamp: ISO 8601 timestamp
    - client_ip: Client IP address
    - api_key_hash: Hashed API key (never full key)
    
    Usage:
        app.wsgi_app = RequestLogger(app.wsgi_app, logger=audit_logger)
    """
    
    def __init__(self, wsgi_app, logger: Optional[logging.Logger] = None):
        """
        Initialize RequestLogger middleware.
        
        Args:
            wsgi_app: WSGI application to wrap
            logger: Logger instance (defaults to 'audit' logger)
        """
        self.wsgi_app = wsgi_app
        self.logger = logger or create_audit_logger("audit")
    
    def __call__(self, environ, start_response):
        """WSGI middleware entry point."""
        start_time = time.time()
        
        # Extract request info
        method = environ.get("REQUEST_METHOD", "?")
        path = environ.get("PATH_INFO", "/")
        client_ip = environ.get("REMOTE_ADDR", "unknown")
        
        # Try to extract API key from Authorization header
        auth_header = environ.get("HTTP_AUTHORIZATION")
        api_key_hash = None
        if auth_header:
            token = extract_bearer_token(auth_header)
            if token:
                api_key_hash = hash_api_key(token)
        
        # Wrap start_response to capture status code
        status_code = [None]
        
        def custom_start_response(status, headers, exc_info=None):
            # Extract status code from status string (e.g., "200 OK" -> 200)
            status_code[0] = int(status.split()[0])
            return start_response(status, headers, exc_info)
        
        try:
            # Call wrapped WSGI app
            result = self.wsgi_app(environ, custom_start_response)
            
            return result
        finally:
            # Log after response (even if exception occurred)
            latency_ms = (time.time() - start_time) * 1000
            
            log_entry = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "method": method,
                "path": path,
                "status_code": status_code[0] or 500,
                "latency_ms": round(latency_ms, 2),
                "client_ip": client_ip,
            }
            
            if api_key_hash:
                log_entry["api_key"] = api_key_hash
            
            self.logger.info(json.dumps(log_entry))


def attach_request_logger(app: Flask, logger: Optional[logging.Logger] = None) -> Flask:
    """
    Attach RequestLogger middleware to a Flask app.
    
    Args:
        app: Flask application instance
        logger: Logger instance (defaults to 'audit' logger)
    
    Returns:
        Modified Flask app with middleware attached
    
    Usage:
        from frontend.middleware import attach_request_logger
        app = Flask(__name__)
        app = attach_request_logger(app)
    """
    audit_logger = logger or create_audit_logger("audit")
    app.wsgi_app = RequestLogger(app.wsgi_app, logger=audit_logger)
    return app


# Module-level logger
logger = logging.getLogger(__name__)
