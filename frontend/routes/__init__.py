#!/usr/bin/env python3
"""
Route blueprints for HallucinationGuard REST API

Provides Flask blueprints for:
- validate: Single and batch validation endpoints
- health: Health check, version info, and policy listing
"""

from flask import Blueprint

# Import route handlers
from frontend.routes.validate import validate_bp
from frontend.routes.health import health_bp

__all__ = ["validate_bp", "health_bp"]
