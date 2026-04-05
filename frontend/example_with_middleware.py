#!/usr/bin/env python3
"""
Example: Using Flask Authentication & Logging Middleware

This demonstrates how to:
1. Add authentication to API endpoints
2. Attach request logging middleware
3. Configure API keys from environment
"""

import os
from flask import Flask, jsonify, request as flask_request
from frontend.middleware import (
    auth_required,
    attach_request_logger,
    create_audit_logger,
)


# Create Flask app
app = Flask(__name__)

# Attach request logger middleware (logs all requests/responses as JSON)
audit_logger = create_audit_logger("api_audit")
app = attach_request_logger(app, logger=audit_logger)


# ============================================================================
# Public Endpoints (no auth required)
# ============================================================================

@app.route('/health', methods=['GET'])
def health_check():
    """Public health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'service': 'GuardlyAI API'
    })


# ============================================================================
# Protected Endpoints (auth required)
# ============================================================================

@app.route('/api/validate', methods=['POST'])
@auth_required
def validate():
    """
    Protected endpoint: Validate LLM output.
    
    Requires: Authorization: Bearer <api_key>
    
    Example:
        curl -X POST http://localhost:5000/api/validate \
          -H "Authorization: Bearer sk-test-key" \
          -H "Content-Type: application/json" \
          -d '{
            "prompt": "What is the capital of France?",
            "output": "The capital of France is Paris.",
            "context": "France is a country in Europe..."
          }'
    """
    try:
        data = flask_request.get_json()
        
        if not data:
            return jsonify({
                'error': 'Invalid request',
                'code': 'INVALID_INPUT',
                'message': 'Request body must be JSON'
            }), 400
        
        prompt = data.get('prompt')
        output = data.get('output')
        
        if not prompt or not output:
            return jsonify({
                'error': 'Invalid request',
                'code': 'INVALID_INPUT',
                'message': 'Missing required fields: prompt, output'
            }), 400
        
        # TODO: Call Guard.validate() here
        # For now, just return a mock response
        return jsonify({
            'decision': 'allow',
            'risk_score': 0.15,
            'evidence': 'Output matches context well',
            'latency_ms': 45
        })
        
    except Exception as e:
        return jsonify({
            'error': 'Validation failed',
            'code': 'VALIDATION_ERROR',
            'message': str(e)
        }), 500


@app.route('/api/batch', methods=['POST'])
@auth_required
def batch_validate():
    """
    Protected endpoint: Validate multiple outputs in batch.
    
    Requires: Authorization: Bearer <api_key>
    
    Example:
        curl -X POST http://localhost:5000/api/batch \
          -H "Authorization: Bearer sk-test-key" \
          -H "Content-Type: application/json" \
          -d '{
            "requests": [
              {
                "id": "req1",
                "prompt": "What is 2+2?",
                "output": "The answer is 4."
              },
              {
                "id": "req2",
                "prompt": "Capital of Germany?",
                "output": "The capital is Berlin."
              }
            ]
          }'
    """
    try:
        data = flask_request.get_json()
        
        if not data or 'requests' not in data:
            return jsonify({
                'error': 'Invalid request',
                'code': 'INVALID_INPUT',
                'message': 'Missing required field: requests'
            }), 400
        
        requests = data.get('requests', [])
        
        # TODO: Process batch validation
        # For now, return mock responses
        results = [
            {
                'id': req.get('id', f'batch_{i}'),
                'decision': 'allow',
                'risk_score': 0.2,
                'latency_ms': 40
            }
            for i, req in enumerate(requests)
        ]
        
        return jsonify({
            'results': results,
            'total': len(results),
            'passed': len(results)
        })
        
    except Exception as e:
        return jsonify({
            'error': 'Batch validation failed',
            'code': 'VALIDATION_ERROR',
            'message': str(e)
        }), 500


# ============================================================================
# Admin Endpoints (optional - could add extra auth checks)
# ============================================================================

@app.route('/api/policies', methods=['GET'])
@auth_required
def get_policies():
    """
    List available validation policies.
    
    Requires: Authorization: Bearer <api_key>
    """
    return jsonify({
        'policies': [
            {
                'name': 'default',
                'description': 'Balanced general-purpose validation'
            },
            {
                'name': 'rag_strict',
                'description': 'Strict validation for RAG systems'
            },
            {
                'name': 'chatbot',
                'description': 'Fast validation for chatbots'
            }
        ]
    })


# ============================================================================
# Error Handlers
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 Not Found."""
    return jsonify({
        'error': 'Not Found',
        'code': 'NOT_FOUND',
        'message': 'The requested endpoint does not exist'
    }), 404


@app.errorhandler(500)
def server_error(error):
    """Handle 500 Internal Server Error."""
    return jsonify({
        'error': 'Internal Server Error',
        'code': 'INTERNAL_ERROR',
        'message': 'An unexpected error occurred'
    }), 500


# ============================================================================
# Configuration & Startup
# ============================================================================

if __name__ == '__main__':
    print("=" * 70)
    print("🔐 GuardlyAI REST API with Authentication & Logging Middleware")
    print("=" * 70)
    
    # Check if API keys are configured
    api_keys = os.getenv('GUARDLY_API_KEYS', '').split(',')
    api_keys = [k.strip() for k in api_keys if k.strip()]
    
    if api_keys:
        print(f"\n✓ API Keys configured: {len(api_keys)} key(s) loaded")
        for i, key in enumerate(api_keys, 1):
            print(f"  {i}. {key[:3]}...{key[-3:]}")
    else:
        print("\n⚠️  No API keys configured (GUARDLY_API_KEYS env var)")
        print("   Development mode: any Bearer token accepted")
        print("   Example: Authorization: Bearer dev-key-12345")
    
    print("\n📝 API Audit Logs:")
    print("   All requests/responses logged as JSON to: api_audit logger")
    print("   Format: {timestamp, method, path, status_code, latency_ms, api_key_hash}")
    
    print("\n🔗 Available Endpoints:")
    print("   GET  /health           (public) - Health check")
    print("   POST /api/validate     (auth)   - Single validation")
    print("   POST /api/batch        (auth)   - Batch validation")
    print("   GET  /api/policies     (auth)   - List policies")
    
    print("\n📘 Testing with cURL:")
    print("   # Unauthenticated (should fail)")
    print("   curl http://localhost:5000/api/validate")
    print()
    print("   # Authenticated")
    print("   curl -H 'Authorization: Bearer dev-key' http://localhost:5000/api/validate")
    
    print("\n" + "=" * 70)
    print("Starting server on http://0.0.0.0:5000")
    print("=" * 70 + "\n")
    
    # Run development server
    app.run(debug=True, host='0.0.0.0', port=5000)
