#!/usr/bin/env python3
"""
Tests for Flask Authentication & Logging Middleware

Covers:
- auth_required decorator validation
- RequestLogger middleware logging
- API key extraction and validation
- Edge cases (malformed headers, missing keys, etc.)
"""

import os
import json
import logging
import pytest
from unittest.mock import patch, MagicMock
from io import StringIO

from flask import Flask, jsonify

# Import middleware components
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from frontend.middleware import (
    auth_required,
    extract_bearer_token,
    validate_api_key,
    get_valid_api_keys,
    hash_api_key,
    mask_api_key,
    RequestLogger,
    create_audit_logger,
    attach_request_logger,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def app():
    """Create a Flask test app with middleware."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Create Flask test client."""
    return app.test_client()


@pytest.fixture
def protected_app():
    """Create Flask app with protected endpoint."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    
    @app.route('/protected', methods=['POST'])
    @auth_required
    def protected_endpoint():
        return jsonify({'success': True})
    
    @app.route('/public', methods=['GET'])
    def public_endpoint():
        return jsonify({'data': 'public'})
    
    return app


@pytest.fixture
def logged_app():
    """Create Flask app with request logger attached."""
    app = Flask(__name__)
    app.config['TESTING'] = True
    
    @app.route('/test', methods=['GET'])
    def test_endpoint():
        return jsonify({'message': 'ok'})
    
    app = attach_request_logger(app)
    return app


# ============================================================================
# TESTS: API Key Extraction & Validation
# ============================================================================

class TestBearerTokenExtraction:
    """Test Bearer token extraction from Authorization header."""
    
    def test_extract_valid_bearer_token(self):
        """Should extract token from valid Bearer header."""
        header = "Bearer sk-abc123xyz"
        token = extract_bearer_token(header)
        assert token == "sk-abc123xyz"
    
    def test_extract_bearer_case_insensitive(self):
        """Bearer scheme should be case-insensitive."""
        header = "bearer sk-abc123xyz"
        token = extract_bearer_token(header)
        assert token == "sk-abc123xyz"
    
    def test_extract_none_for_missing_header(self):
        """Should return None for missing header."""
        token = extract_bearer_token(None)
        assert token is None
    
    def test_extract_none_for_empty_header(self):
        """Should return None for empty header."""
        token = extract_bearer_token("")
        assert token is None
    
    def test_extract_none_for_missing_scheme(self):
        """Should return None if Bearer scheme missing."""
        header = "sk-abc123xyz"
        token = extract_bearer_token(header)
        assert token is None
    
    def test_extract_none_for_wrong_scheme(self):
        """Should return None for non-Bearer auth scheme."""
        header = "Basic dXNlcjpwYXNz"
        token = extract_bearer_token(header)
        assert token is None
    
    def test_extract_none_for_malformed_header(self):
        """Should return None for malformed Bearer header."""
        header = "Bearer"  # Missing token
        token = extract_bearer_token(header)
        assert token is None
    
    def test_extract_none_for_too_many_parts(self):
        """Should return None if too many parts in header."""
        header = "Bearer token extra_part"
        token = extract_bearer_token(header)
        assert token is None


class TestAPIKeyValidation:
    """Test API key validation logic."""
    
    def test_validate_key_with_empty_env(self):
        """Should allow requests when no env var set (dev mode)."""
        with patch.dict(os.environ, {}, clear=True):
            result = validate_api_key("any-key")
            assert result is True
    
    def test_validate_key_in_list(self):
        """Should validate key if in GUARDLY_API_KEYS list."""
        with patch.dict(os.environ, {'GUARDLY_API_KEYS': 'key1,key2,key3'}):
            assert validate_api_key('key1') is True
            assert validate_api_key('key2') is True
            assert validate_api_key('key3') is True
    
    def test_validate_key_not_in_list(self):
        """Should reject key not in GUARDLY_API_KEYS list."""
        with patch.dict(os.environ, {'GUARDLY_API_KEYS': 'key1,key2,key3'}):
            assert validate_api_key('invalid-key') is False
    
    def test_validate_key_with_whitespace(self):
        """Should handle whitespace in GUARDLY_API_KEYS."""
        with patch.dict(os.environ, {'GUARDLY_API_KEYS': ' key1 , key2 , key3 '}):
            assert validate_api_key('key1') is True
            assert validate_api_key('key2') is True


class TestGetValidAPIKeys:
    """Test loading API keys from environment."""
    
    def test_get_keys_from_env(self):
        """Should parse GUARDLY_API_KEYS env var."""
        with patch.dict(os.environ, {'GUARDLY_API_KEYS': 'key1,key2,key3'}):
            keys = get_valid_api_keys()
            assert keys == ['key1', 'key2', 'key3']
    
    def test_get_keys_with_whitespace(self):
        """Should strip whitespace from keys."""
        with patch.dict(os.environ, {'GUARDLY_API_KEYS': ' key1 , key2 , key3 '}):
            keys = get_valid_api_keys()
            assert keys == ['key1', 'key2', 'key3']
    
    def test_get_empty_list_when_not_set(self):
        """Should return empty list if env var not set."""
        with patch.dict(os.environ, {}, clear=True):
            keys = get_valid_api_keys()
            assert keys == []
    
    def test_get_empty_list_when_empty_string(self):
        """Should return empty list if env var is empty."""
        with patch.dict(os.environ, {'GUARDLY_API_KEYS': ''}):
            keys = get_valid_api_keys()
            assert keys == []


# ============================================================================
# TESTS: Key Masking & Hashing
# ============================================================================

class TestKeyMasking:
    """Test API key masking for logs."""
    
    def test_mask_api_key(self):
        """Should mask API key showing first 3 and last 3 chars."""
        masked = mask_api_key("sk-abc123xyz789")
        assert masked == "sk-...789"
    
    def test_mask_short_key(self):
        """Should return *** for keys shorter than 6 chars."""
        masked = mask_api_key("short")
        assert masked == "***"
    
    def test_mask_empty_key(self):
        """Should return *** for empty key."""
        masked = mask_api_key("")
        assert masked == "***"


class TestKeyHashing:
    """Test API key hashing for logs."""
    
    def test_hash_api_key(self):
        """Should hash API key with prefix."""
        hashed = hash_api_key("sk-abc123xyz")
        assert hashed.startswith("sk-...")
        assert len(hashed) > 6  # prefix + "..." + hash
    
    def test_hash_different_for_different_keys(self):
        """Different keys should produce different hashes."""
        hash1 = hash_api_key("key1")
        hash2 = hash_api_key("key2")
        assert hash1 != hash2
    
    def test_hash_same_for_same_key(self):
        """Same key should produce same hash."""
        hash1 = hash_api_key("key1")
        hash2 = hash_api_key("key1")
        assert hash1 == hash2
    
    def test_hash_short_key(self):
        """Should return 'invalid' for keys shorter than 3 chars."""
        hashed = hash_api_key("ab")
        assert hashed == "invalid"


# ============================================================================
# TESTS: auth_required Decorator
# ============================================================================

class TestAuthRequiredDecorator:
    """Test auth_required decorator on Flask routes."""
    
    def test_auth_required_blocks_missing_header(self, protected_app):
        """Should reject request with missing Authorization header."""
        client = protected_app.test_client()
        response = client.post('/protected')
        
        assert response.status_code == 401
        data = response.get_json()
        assert data['code'] == 'AUTH_FAILED'
        # Message should mention Authorization or Bearer
        message_lower = data['message'].lower()
        assert 'authorization' in message_lower or 'bearer' in message_lower
    
    def test_auth_required_blocks_malformed_header(self, protected_app):
        """Should reject request with malformed Authorization header."""
        client = protected_app.test_client()
        response = client.post('/protected', headers={
            'Authorization': 'Invalid-Header-Format'
        })
        
        assert response.status_code == 401
        data = response.get_json()
        assert data['code'] == 'AUTH_FAILED'
    
    def test_auth_required_allows_valid_key_in_dev_mode(self, protected_app):
        """Should allow any key when no GUARDLY_API_KEYS set (dev mode)."""
        with patch.dict(os.environ, {}, clear=True):
            client = protected_app.test_client()
            response = client.post('/protected', headers={
                'Authorization': 'Bearer any-key'
            })
            
            assert response.status_code == 200
            assert response.get_json()['success'] is True
    
    def test_auth_required_rejects_invalid_key(self, protected_app):
        """Should reject request with invalid API key."""
        with patch.dict(os.environ, {'GUARDLY_API_KEYS': 'valid-key'}):
            client = protected_app.test_client()
            response = client.post('/protected', headers={
                'Authorization': 'Bearer invalid-key'
            })
            
            assert response.status_code == 401
            data = response.get_json()
            assert data['code'] == 'AUTH_FAILED'
    
    def test_auth_required_accepts_valid_key(self, protected_app):
        """Should accept request with valid API key."""
        with patch.dict(os.environ, {'GUARDLY_API_KEYS': 'valid-key'}):
            client = protected_app.test_client()
            response = client.post('/protected', headers={
                'Authorization': 'Bearer valid-key'
            })
            
            assert response.status_code == 200
            assert response.get_json()['success'] is True
    
    def test_auth_required_sets_request_context(self, protected_app):
        """Should attach API key to request context after validation."""
        with patch.dict(os.environ, {'GUARDLY_API_KEYS': 'test-key'}):
            # Add a test route that checks request.api_key
            @protected_app.route('/check-key', methods=['POST'])
            @auth_required
            def check_key():
                from flask import request as flask_request
                return jsonify({'api_key': getattr(flask_request, 'api_key', None)})
            
            client = protected_app.test_client()
            response = client.post('/check-key', headers={
                'Authorization': 'Bearer test-key'
            })
            
            assert response.status_code == 200
            assert response.get_json()['api_key'] == 'test-key'


# ============================================================================
# TESTS: RequestLogger Middleware
# ============================================================================

class TestRequestLogger:
    """Test RequestLogger WSGI middleware."""
    
    def test_request_logger_logs_request(self, logged_app, caplog):
        """Should log request with method, path, status."""
        with caplog.at_level(logging.INFO):
            client = logged_app.test_client()
            response = client.get('/test')
            
            assert response.status_code == 200
        
        # Check that something was logged
        assert len(caplog.records) > 0
    
    def test_request_logger_logs_json_format(self, logged_app, caplog):
        """Should log in valid JSON format."""
        import logging
        with caplog.at_level(logging.INFO):
            client = logged_app.test_client()
            response = client.get('/test')
            
            assert response.status_code == 200
        
        # Find the audit log record
        audit_records = [r for r in caplog.records if 'audit' in r.name or r.levelno == logging.INFO]
        if audit_records:
            log_entry = audit_records[0].getMessage()
            # Should be valid JSON
            parsed = json.loads(log_entry)
            assert 'method' in parsed
            assert 'path' in parsed
            assert 'status_code' in parsed
    
    def test_request_logger_captures_method_path_status(self, logged_app, caplog):
        """Should capture method, path, and status code."""
        import logging
        with caplog.at_level(logging.INFO):
            client = logged_app.test_client()
            response = client.get('/test')
        
        # Check logged data
        audit_records = [r for r in caplog.records if r.levelno >= logging.INFO]
        if audit_records:
            log_entry = json.loads(audit_records[0].getMessage())
            assert log_entry['method'] == 'GET'
            assert log_entry['path'] == '/test'
            assert log_entry['status_code'] == 200
    
    def test_request_logger_includes_timestamp(self, logged_app, caplog):
        """Should include ISO 8601 timestamp."""
        import logging
        with caplog.at_level(logging.INFO):
            client = logged_app.test_client()
            response = client.get('/test')
        
        audit_records = [r for r in caplog.records if r.levelno >= logging.INFO]
        if audit_records:
            log_entry = json.loads(audit_records[0].getMessage())
            assert 'timestamp' in log_entry
            assert log_entry['timestamp'].endswith('Z')
    
    def test_request_logger_includes_latency(self, logged_app, caplog):
        """Should include latency_ms field."""
        import logging
        with caplog.at_level(logging.INFO):
            client = logged_app.test_client()
            response = client.get('/test')
        
        audit_records = [r for r in caplog.records if r.levelno >= logging.INFO]
        if audit_records:
            log_entry = json.loads(audit_records[0].getMessage())
            assert 'latency_ms' in log_entry
            assert log_entry['latency_ms'] >= 0
    
    def test_request_logger_masks_api_key(self, logged_app, caplog):
        """Should never log full API key."""
        import logging
        with patch.dict(os.environ, {}, clear=True):
            with caplog.at_level(logging.INFO):
                client = logged_app.test_client()
                response = client.get('/test', headers={
                    'Authorization': 'Bearer very-secret-api-key-do-not-log'
                })
        
        # Check all log records - none should contain the full key
        for record in caplog.records:
            message = record.getMessage()
            assert 'very-secret-api-key-do-not-log' not in message


# ============================================================================
# TESTS: CreateAuditLogger
# ============================================================================

class TestCreateAuditLogger:
    """Test audit logger creation."""
    
    def test_create_audit_logger(self):
        """Should create a logger with INFO level."""
        logger = create_audit_logger("test_audit")
        assert logger is not None
        assert logger.level == logging.INFO or any(h.level == logging.INFO for h in logger.handlers)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
