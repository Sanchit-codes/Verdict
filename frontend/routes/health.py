#!/usr/bin/env python3
"""
Health & Info Routes - GET /health, GET /version, GET /config/policies

Provides:
- Health check with validator status
- Version information for all dependencies
- List of available policies
"""

import logging
import sys
from datetime import datetime

from flask import Blueprint, jsonify
import transformers
import torch

from frontend.schemas import (
    HealthCheckResponse,
    VersionResponse,
    PoliciesResponse,
    PolicyMetadata,
)
from frontend.service import GuardService


logger = logging.getLogger(__name__)

health_bp = Blueprint("health", __name__)

# Global service instance
_guard_service = None


def get_guard_service() -> GuardService:
    """Get or create global GuardService instance."""
    global _guard_service
    if _guard_service is None:
        _guard_service = GuardService()
    return _guard_service


# ============================================================================
# GET /health - Health Check
# ============================================================================


@health_bp.route("/health", methods=["GET"])
def health_check():
    """
    Check system health and validator availability.
    
    Response (200 OK):
    {
        "status": "healthy|degraded|unhealthy",
        "timestamp": "2025-01-10T12:00:00Z",
        "validators": {
            "heuristics": {"available": true, "latency_ms": 2},
            "embedding": {"available": true, "latency_ms": 25},
            "hhem": {"available": true, "latency_ms": 45}
        },
        "uptime_seconds": 3600,
        "requests_processed": 150
    }
    
    Status Meanings:
    - healthy: All validators available
    - degraded: Some validators unavailable (graceful fallback active)
    - unhealthy: No validators available
    """
    try:
        guard_service = get_guard_service()
        health_status = guard_service.get_health_status()
        
        response = HealthCheckResponse(
            status=health_status["status"],
            timestamp=datetime.utcnow().isoformat() + "Z",
            validators=health_status.get("validators", {}),
            uptime_seconds=health_status["uptime_seconds"],
            requests_processed=health_status["requests_processed"],
        )
        
        # Return 200 for all statuses (health check itself succeeded)
        return jsonify(response.model_dump(exclude_none=True)), 200
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        
        # Still return a response, even if unhealthy
        response = HealthCheckResponse(
            status="unhealthy",
            timestamp=datetime.utcnow().isoformat() + "Z",
            validators={},
            uptime_seconds=0,
            requests_processed=0,
        )
        
        return jsonify(response.model_dump()), 200


# ============================================================================
# GET /version - Version Information
# ============================================================================


@health_bp.route("/version", methods=["GET"])
def version_info():
    """
    Get version information for API and all dependencies.
    
    Response (200 OK):
    {
        "api_version": "1.0.0",
        "sdk_version": "1.0.0",
        "python_version": "3.10.5",
        "transformers_version": "4.44.0",
        "torch_version": "2.3.0",
        "policy_schema_version": "1.0"
    }
    """
    try:
        # Import SDK version
        try:
            import hallucination_guard
            sdk_version = getattr(hallucination_guard, "__version__", "unknown")
        except Exception:
            sdk_version = "unknown"
        
        response = VersionResponse(
            api_version="1.0.0",
            sdk_version=sdk_version,
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            transformers_version=transformers.__version__,
            torch_version=torch.__version__,
            policy_schema_version="1.0",
        )
        
        logger.debug(f"Version info requested: sdk={sdk_version}, python={sys.version}")
        
        return jsonify(response.model_dump()), 200
    
    except Exception as e:
        logger.error(f"Failed to get version info: {e}")
        
        # Return best-effort response
        response = VersionResponse(
            api_version="1.0.0",
            sdk_version="unknown",
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            transformers_version="unknown",
            torch_version="unknown",
            policy_schema_version="1.0",
        )
        
        return jsonify(response.model_dump()), 200


# ============================================================================
# GET /config/policies - List Available Policies
# ============================================================================


@health_bp.route("/config/policies", methods=["GET"])
def list_policies():
    """
    Get list of available policies with metadata.
    
    Response (200 OK):
    {
        "policies": [
            {
                "name": "default",
                "description": "Balanced general-purpose policy",
                "risk_threshold": 0.5,
                "validators_enabled": ["heuristics", "embedding", "hhem"],
                "latency_budget_ms": 100
            },
            {
                "name": "rag_strict",
                "description": "High-risk domains (healthcare, finance)",
                "risk_threshold": 0.3,
                "validators_enabled": ["heuristics", "embedding", "hhem"],
                "latency_budget_ms": 150
            },
            {
                "name": "chatbot",
                "description": "Low-latency chatbot policy",
                "risk_threshold": 0.7,
                "validators_enabled": ["heuristics", "embedding"],
                "latency_budget_ms": 50
            }
        ]
    }
    """
    try:
        guard_service = get_guard_service()
        policies_list = guard_service.get_policies()
        
        # Convert to PolicyMetadata objects
        policy_objects = [
            PolicyMetadata(
                name=p["name"],
                description=p.get("description", ""),
                risk_threshold=p.get("risk_threshold", 0.5),
                validators_enabled=p.get("validators_enabled", []),
                latency_budget_ms=p.get("latency_budget_ms", 100),
            )
            for p in policies_list
        ]
        
        response = PoliciesResponse(policies=policy_objects)
        
        logger.debug(f"Policies requested: {len(policy_objects)} policies available")
        
        return jsonify(response.model_dump()), 200
    
    except Exception as e:
        logger.error(f"Failed to get policies: {e}")
        
        # Return empty list on error
        response = PoliciesResponse(policies=[])
        
        return jsonify(response.model_dump()), 200
