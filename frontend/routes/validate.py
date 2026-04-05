#!/usr/bin/env python3
"""
Validation Routes - POST /validate and POST /validate/batch

Handles:
- Single validation requests with response validation
- Batch validation with parallel/sequential execution
- Error handling with proper HTTP status codes
"""

import logging
from datetime import datetime

from flask import Blueprint, request, jsonify
from pydantic import ValidationError

from frontend.middleware import auth_required
from frontend.schemas import (
    ValidateRequest,
    BatchValidateRequest,
)
from frontend.service import GuardService, BatchProcessor
from frontend.errors import (
    error_response,
    validation_error_response,
    generate_request_id,
)


logger = logging.getLogger(__name__)

validate_bp = Blueprint("validate", __name__)

# Global service instances
_guard_service = None
_batch_processor = None


def get_guard_service() -> GuardService:
    """Get or create global GuardService instance."""
    global _guard_service
    if _guard_service is None:
        _guard_service = GuardService()
    return _guard_service


def get_batch_processor() -> BatchProcessor:
    """Get or create global BatchProcessor instance."""
    global _batch_processor
    if _batch_processor is None:
        service = get_guard_service()
        _batch_processor = BatchProcessor(service)
    return _batch_processor


# ============================================================================
# POST /validate - Single Validation
# ============================================================================


@validate_bp.route("/validate", methods=["POST"])
@auth_required
def validate_single():
    """
    Validate a single LLM output.
    
    Request body (JSON):
    {
        "prompt": "User query (required)",
        "output": "LLM response (required)",
        "context": "Reference text (optional)",
        "policy": "Policy name (optional, default: 'default')",
        "domain": "Domain/category (optional, default: 'general')",
        "use_refinement": "Include preprocessing metadata (optional, default: false)"
    }
    
    Response (200 OK):
    {
        "decision": "allow|block|regenerate|abstain",
        "risk_score": 0.0-1.0,
        "confidence": 0.0-1.0,
        "evidence": "Human-readable explanation",
        "output": "Validated output (optional)",
        "suggested_fix": "Regeneration hint if decision=regenerate (optional)",
        "latency_ms": 45,
        "policy_name": "rag_strict",
        "tier_results": [...],
        "preprocessing_metadata": {...}
    }
    
    Error Responses:
    - 400 (INVALID_INPUT): Missing or malformed required fields
    - 422 (VALIDATION_ERROR): Field validation failed
    - 503 (SERVICE_DEGRADED): Validator failure or timeout
    """
    request_id = generate_request_id()
    
    try:
        # Parse and validate request
        request_data = request.get_json()
        
        if not request_data:
            response, status = error_response(
                status_code=400,
                code="INVALID_INPUT",
                message="Request body must be valid JSON",
                request_id=request_id,
            )
            return jsonify(response), status
        
        try:
            validate_request = ValidateRequest(**request_data)
        except ValidationError as e:
            response, status = validation_error_response(e, request_id)
            return jsonify(response), status
        
        # Call service
        guard_service = get_guard_service()
        
        try:
            validation_response = guard_service.validate(validate_request)
            
            logger.info(
                f"Validation successful: request_id={request_id}, "
                f"decision={validation_response.decision}, "
                f"risk_score={validation_response.risk_score:.2f}"
            )
            
            return jsonify(validation_response.model_dump(exclude_none=True)), 200
        
        except Exception as e:
            logger.error(f"Validation service error: {e}")
            response, status = error_response(
                status_code=503,
                code="SERVICE_DEGRADED",
                message="Validation service encountered an error",
                request_id=request_id,
            )
            return jsonify(response), status
    
    except Exception as e:
        logger.error(f"Unexpected error in /validate: {e}")
        response, status = error_response(
            status_code=500,
            code="INTERNAL_ERROR",
            message="Unexpected server error",
            request_id=request_id,
        )
        return jsonify(response), status


# ============================================================================
# POST /validate/batch - Batch Validation
# ============================================================================


@validate_bp.route("/validate/batch", methods=["POST"])
@auth_required
def validate_batch():
    """
    Validate multiple LLM outputs in parallel or sequential mode.
    
    Request body (JSON):
    {
        "requests": [
            {
                "id": "Request ID for tracking (optional, auto-generated)",
                "prompt": "User query (required)",
                "output": "LLM response (required)",
                "context": "Reference text (optional)",
                "policy": "Policy name (optional)",
                "domain": "Domain/category (optional)",
                "use_refinement": "Include preprocessing metadata (optional)"
            },
            ...
        ],
        "mode": "parallel|sequential (optional, default: 'parallel')",
        "timeout_per_request_ms": 30000 (optional, default: 30000, range: 1000-120000)
    }
    
    Response (200 OK):
    {
        "batch_id": "batch_123456",
        "total_requests": 10,
        "successful_validations": 9,
        "failed_validations": 1,
        "results": [
            {
                "id": "req_id_1",
                "decision": "allow",
                "risk_score": 0.2,
                "confidence": 0.95,
                "evidence": "High confidence hallucination detection",
                "latency_ms": 45,
                "error": null
            },
            {
                "id": "req_id_2",
                "decision": null,
                "risk_score": null,
                "confidence": null,
                "evidence": null,
                "latency_ms": 100,
                "error": "Validation timeout"
            }
        ],
        "batch_latency_ms": 200
    }
    
    Error Responses:
    - 400 (INVALID_INPUT): Missing or malformed requests array
    - 422 (VALIDATION_ERROR): Request validation failed
    - 503 (SERVICE_DEGRADED): Batch processor failure
    """
    request_id = generate_request_id()
    
    try:
        # Parse and validate request
        request_data = request.get_json()
        
        if not request_data:
            response, status = error_response(
                status_code=400,
                code="INVALID_INPUT",
                message="Request body must be valid JSON",
                request_id=request_id,
            )
            return jsonify(response), status
        
        try:
            batch_request = BatchValidateRequest(**request_data)
        except ValidationError as e:
            response, status = validation_error_response(e, request_id)
            return jsonify(response), status
        
        # Call batch processor
        batch_processor = get_batch_processor()
        
        try:
            batch_response = batch_processor.process_batch(
                items=batch_request.requests,
                mode=batch_request.mode,
                timeout_per_request_ms=batch_request.timeout_per_request_ms,
            )
            
            logger.info(
                f"Batch validation complete: request_id={request_id}, "
                f"batch_id={batch_response.batch_id}, "
                f"successful={batch_response.successful_validations}, "
                f"failed={batch_response.failed_validations}"
            )
            
            return jsonify(batch_response.model_dump(exclude_none=True)), 200
        
        except Exception as e:
            logger.error(f"Batch processor error: {e}")
            response, status = error_response(
                status_code=503,
                code="SERVICE_DEGRADED",
                message="Batch processor encountered an error",
                request_id=request_id,
            )
            return jsonify(response), status
    
    except Exception as e:
        logger.error(f"Unexpected error in /validate/batch: {e}")
        response, status = error_response(
            status_code=500,
            code="INTERNAL_ERROR",
            message="Unexpected server error",
            request_id=request_id,
        )
        return jsonify(response), status
