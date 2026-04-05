#!/usr/bin/env python3
"""
Tests for HallucinationGuard REST API Routes

Covers:
- POST /validate: Single validation endpoint
- POST /validate/batch: Batch validation with parallel/sequential modes
- GET /health: Health check status
- GET /version: Version information
- GET /config/policies: List available policies
- Authentication (auth_required decorator)
- Error handling with proper HTTP status codes
"""

import os
import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask
from hallucination_guard.core.decision import GuardDecision

from frontend.routes import validate_bp, health_bp
from frontend.schemas import ValidateRequest, ValidationResponse
from frontend.service import GuardService, BatchProcessor


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def app():
    """Create a Flask test app with routes."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    
    # Register blueprints
    app.register_blueprint(validate_bp)
    app.register_blueprint(health_bp)
    
    return app


@pytest.fixture
def client(app):
    """Create a Flask test client."""
    return app.test_client()


@pytest.fixture
def auth_header():
    """Valid authentication header (no key validation in test mode)."""
    return {"Authorization": "Bearer test-key-123"}


# ============================================================================
# Test POST /validate - Single Validation
# ============================================================================


class TestValidateSingleEndpoint:
    """Tests for POST /validate endpoint."""
    
    def test_validate_single_success(self, client, auth_header):
        """Test successful single validation."""
        request_data = {
            "prompt": "What is the capital of France?",
            "output": "The capital of France is Paris.",
            "context": "France is a country in Europe. Its capital is Paris.",
            "policy": "default",
            "domain": "geography",
            "use_refinement": False,
        }
        
        with patch('frontend.routes.validate.GuardService.validate') as mock_validate:
            # Mock the validation response
            mock_response = ValidationResponse(
                decision="allow",
                risk_score=0.1,
                confidence=0.95,
                evidence="High context overlap",
                latency_ms=45.0,
                policy_name="default",
            )
            mock_validate.return_value = mock_response
            
            response = client.post(
                "/validate",
                json=request_data,
                headers=auth_header,
            )
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["decision"] == "allow"
            assert data["risk_score"] == 0.1
            assert data["confidence"] == 0.95
    
    def test_validate_missing_prompt(self, client, auth_header):
        """Test validation with missing prompt (400 - INVALID_INPUT)."""
        request_data = {
            "output": "Some output",
        }
        
        response = client.post(
            "/validate",
            json=request_data,
            headers=auth_header,
        )
        
        assert response.status_code == 422  # Pydantic validation error
        data = response.get_json()
        assert data["code"] == "VALIDATION_ERROR"
    
    def test_validate_invalid_policy(self, client, auth_header):
        """Test validation with invalid policy."""
        request_data = {
            "prompt": "What is AI?",
            "output": "AI is artificial intelligence",
            "policy": "nonexistent_policy",
        }
        
        with patch('frontend.routes.validate.GuardService.validate') as mock_validate:
            from hallucination_guard.core.exceptions import PolicyLoadError
            mock_validate.side_effect = PolicyLoadError("nonexistent_policy", "Policy not found")
            
            response = client.post(
                "/validate",
                json=request_data,
                headers=auth_header,
            )
            
            assert response.status_code == 503  # SERVICE_DEGRADED
            data = response.get_json()
            assert data["code"] == "SERVICE_DEGRADED"
    
    def test_validate_missing_auth(self, client):
        """Test validation without authentication."""
        request_data = {
            "prompt": "What is AI?",
            "output": "AI is intelligence",
        }
        
        response = client.post(
            "/validate",
            json=request_data,
        )
        
        assert response.status_code == 401
        data = response.get_json()
        assert data["code"] == "AUTH_FAILED"
    
    def test_validate_empty_body(self, client, auth_header):
        """Test validation with empty JSON body returns INVALID_INPUT."""
        # Empty dict is treated as "no body content"
        response = client.post(
            "/validate",
            json={},
            headers=auth_header,
        )
        
        # Should be 400 (INVALID_INPUT) when body is empty/missing content
        assert response.status_code == 400
        data = response.get_json()
        assert data["code"] == "INVALID_INPUT"


# ============================================================================
# Test POST /validate/batch - Batch Validation
# ============================================================================


class TestValidateBatchEndpoint:
    """Tests for POST /validate/batch endpoint."""
    
    def test_batch_validate_parallel(self, client, auth_header):
        """Test batch validation in parallel mode."""
        request_data = {
            "requests": [
                {
                    "id": "req_1",
                    "prompt": "Q1",
                    "output": "A1",
                    "context": "Context 1",
                },
                {
                    "id": "req_2",
                    "prompt": "Q2",
                    "output": "A2",
                    "context": "Context 2",
                },
            ],
            "mode": "parallel",
            "timeout_per_request_ms": 30000,
        }
        
        with patch('frontend.routes.validate.get_batch_processor') as mock_get_processor:
            from frontend.schemas import BatchValidationResponse, BatchValidationResultItem
            
            mock_processor = MagicMock()
            mock_get_processor.return_value = mock_processor
            
            mock_response = BatchValidationResponse(
                batch_id="batch_001",
                total_requests=2,
                successful_validations=2,
                failed_validations=0,
                results=[
                    BatchValidationResultItem(
                        id="req_1",
                        decision="allow",
                        risk_score=0.1,
                        confidence=0.95,
                        evidence="OK",
                        latency_ms=45.0,
                    ),
                    BatchValidationResultItem(
                        id="req_2",
                        decision="block",
                        risk_score=0.8,
                        confidence=0.90,
                        evidence="Hallucination detected",
                        latency_ms=50.0,
                    ),
                ],
                batch_latency_ms=100.0,
            )
            mock_processor.process_batch.return_value = mock_response
            
            response = client.post(
                "/validate/batch",
                json=request_data,
                headers=auth_header,
            )
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["batch_id"] == "batch_001"
            assert data["total_requests"] == 2
            assert data["successful_validations"] == 2
            assert data["failed_validations"] == 0
            assert len(data["results"]) == 2
    
    def test_batch_validate_sequential(self, client, auth_header):
        """Test batch validation in sequential mode."""
        request_data = {
            "requests": [
                {
                    "prompt": "Q1",
                    "output": "A1",
                },
            ],
            "mode": "sequential",
            "timeout_per_request_ms": 30000,
        }
        
        with patch('frontend.routes.validate.get_batch_processor') as mock_get_processor:
            from frontend.schemas import BatchValidationResponse, BatchValidationResultItem
            
            mock_processor = MagicMock()
            mock_get_processor.return_value = mock_processor
            
            mock_response = BatchValidationResponse(
                batch_id="batch_002",
                total_requests=1,
                successful_validations=1,
                failed_validations=0,
                results=[
                    BatchValidationResultItem(
                        id="req_1",
                        decision="allow",
                        risk_score=0.2,
                        confidence=0.9,
                        evidence="OK",
                        latency_ms=40.0,
                    ),
                ],
                batch_latency_ms=40.0,
            )
            mock_processor.process_batch.return_value = mock_response
            
            response = client.post(
                "/validate/batch",
                json=request_data,
                headers=auth_header,
            )
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["batch_id"] == "batch_002"
    
    def test_batch_empty_requests(self, client, auth_header):
        """Test batch with empty requests array."""
        request_data = {
            "requests": [],
        }
        
        response = client.post(
            "/validate/batch",
            json=request_data,
            headers=auth_header,
        )
        
        assert response.status_code == 422  # Validation error
        data = response.get_json()
        assert data["code"] == "VALIDATION_ERROR"
    
    def test_batch_partial_failure(self, client, auth_header):
        """Test batch with partial failures."""
        request_data = {
            "requests": [
                {"id": "req_1", "prompt": "Q1", "output": "A1"},
                {"id": "req_2", "prompt": "Q2", "output": "A2"},
            ],
        }
        
        with patch('frontend.routes.validate.get_batch_processor') as mock_get_processor:
            from frontend.schemas import BatchValidationResponse, BatchValidationResultItem
            
            mock_processor = MagicMock()
            mock_get_processor.return_value = mock_processor
            
            mock_response = BatchValidationResponse(
                batch_id="batch_003",
                total_requests=2,
                successful_validations=1,
                failed_validations=1,
                results=[
                    BatchValidationResultItem(
                        id="req_1",
                        decision="allow",
                        risk_score=0.1,
                        confidence=0.95,
                        evidence="OK",
                        latency_ms=45.0,
                    ),
                    BatchValidationResultItem(
                        id="req_2",
                        decision=None,
                        risk_score=None,
                        confidence=None,
                        evidence=None,
                        latency_ms=100.0,
                        error="Validation timeout",
                    ),
                ],
                batch_latency_ms=150.0,
            )
            mock_processor.process_batch.return_value = mock_response
            
            response = client.post(
                "/validate/batch",
                json=request_data,
                headers=auth_header,
            )
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["successful_validations"] == 1
            assert data["failed_validations"] == 1
            
            # Check result items
            results = data["results"]
            assert results[0]["decision"] == "allow"
            # decision field is excluded when None (from exclude_none=True)
            assert results[1].get("decision") is None
            assert results[1]["error"] == "Validation timeout"


# ============================================================================
# Test GET /health - Health Check
# ============================================================================


class TestHealthCheckEndpoint:
    """Tests for GET /health endpoint."""
    
    def test_health_check_healthy(self, client):
        """Test health check when system is healthy."""
        with patch('frontend.routes.health.get_guard_service') as mock_get_service:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service
            mock_service.get_health_status.return_value = {
                "status": "healthy",
                "validators": {
                    "heuristics": {"available": True, "latency_ms": 2},
                    "embedding": {"available": True, "latency_ms": 25},
                    "hhem": {"available": True, "latency_ms": 45},
                },
                "uptime_seconds": 3600,
                "requests_processed": 150,
            }
            
            response = client.get("/health")
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "healthy"
            assert "heuristics" in data["validators"]
            assert data["uptime_seconds"] == 3600
            assert data["requests_processed"] == 150
    
    def test_health_check_degraded(self, client):
        """Test health check when system is degraded."""
        with patch('frontend.routes.health.get_guard_service') as mock_get_service:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service
            mock_service.get_health_status.return_value = {
                "status": "degraded",
                "validators": {
                    "heuristics": {"available": True, "latency_ms": 2},
                    "embedding": {"available": False, "error": "Model not loaded"},
                    "hhem": {"available": True, "latency_ms": 45},
                },
                "uptime_seconds": 3600,
                "requests_processed": 150,
            }
            
            response = client.get("/health")
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["status"] == "degraded"
    
    def test_health_check_includes_timestamp(self, client):
        """Test that health check includes ISO 8601 timestamp."""
        with patch('frontend.routes.health.get_guard_service') as mock_get_service:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service
            mock_service.get_health_status.return_value = {
                "status": "healthy",
                "validators": {},
                "uptime_seconds": 0,
                "requests_processed": 0,
            }
            
            response = client.get("/health")
            
            assert response.status_code == 200
            data = response.get_json()
            assert "timestamp" in data
            # Should be ISO 8601 format
            assert data["timestamp"].endswith("Z")


# ============================================================================
# Test GET /version - Version Information
# ============================================================================


class TestVersionEndpoint:
    """Tests for GET /version endpoint."""
    
    def test_version_endpoint(self, client):
        """Test version endpoint returns all required fields."""
        response = client.get("/version")
        
        assert response.status_code == 200
        data = response.get_json()
        
        # Check all required fields
        assert "api_version" in data
        assert "sdk_version" in data
        assert "python_version" in data
        assert "transformers_version" in data
        assert "torch_version" in data
        assert "policy_schema_version" in data
        
        # Check formats
        assert isinstance(data["api_version"], str)
        assert isinstance(data["python_version"], str)
        assert isinstance(data["policy_schema_version"], str)


# ============================================================================
# Test GET /config/policies - List Policies
# ============================================================================


class TestPoliciesEndpoint:
    """Tests for GET /config/policies endpoint."""
    
    def test_list_policies_success(self, client):
        """Test listing available policies."""
        with patch('frontend.routes.health.get_guard_service') as mock_get_service:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service
            mock_service.get_policies.return_value = [
                {
                    "name": "default",
                    "description": "Balanced policy",
                    "risk_threshold": 0.5,
                    "validators_enabled": ["heuristics", "embedding", "hhem"],
                    "latency_budget_ms": 100,
                },
                {
                    "name": "rag_strict",
                    "description": "Strict policy for high-risk domains",
                    "risk_threshold": 0.3,
                    "validators_enabled": ["heuristics", "embedding", "hhem"],
                    "latency_budget_ms": 150,
                },
            ]
            
            response = client.get("/config/policies")
            
            assert response.status_code == 200
            data = response.get_json()
            assert "policies" in data
            assert len(data["policies"]) == 2
            
            # Check first policy
            policy = data["policies"][0]
            assert policy["name"] == "default"
            assert policy["risk_threshold"] == 0.5
            assert "heuristics" in policy["validators_enabled"]
    
    def test_list_policies_empty(self, client):
        """Test policies endpoint when no policies are available."""
        with patch('frontend.routes.health.get_guard_service') as mock_get_service:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service
            mock_service.get_policies.return_value = []
            
            response = client.get("/config/policies")
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["policies"] == []


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for route handlers."""
    
    def test_auth_required_on_validate(self, client):
        """Test that /validate requires authentication."""
        response = client.post(
            "/validate",
            json={
                "prompt": "What is AI?",
                "output": "AI is intelligence",
            },
        )
        
        assert response.status_code == 401
    
    def test_health_no_auth_required(self, client):
        """Test that /health does not require authentication."""
        with patch('frontend.routes.health.get_guard_service') as mock_get_service:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service
            mock_service.get_health_status.return_value = {
                "status": "healthy",
                "validators": {},
                "uptime_seconds": 0,
                "requests_processed": 0,
            }
            
            response = client.get("/health")
            
            # Should succeed without auth header
            assert response.status_code == 200
    
    def test_version_no_auth_required(self, client):
        """Test that /version does not require authentication."""
        response = client.get("/version")
        
        # Should succeed without auth header
        assert response.status_code == 200
    
    def test_policies_no_auth_required(self, client):
        """Test that /config/policies does not require authentication."""
        with patch('frontend.routes.health.get_guard_service') as mock_get_service:
            mock_service = MagicMock()
            mock_get_service.return_value = mock_service
            mock_service.get_policies.return_value = []
            
            response = client.get("/config/policies")
            
            # Should succeed without auth header
            assert response.status_code == 200
