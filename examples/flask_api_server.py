#!/usr/bin/env python3
"""
Standalone GuardlyAI REST API Server

A production-ready Flask server that wraps the HallucinationGuard SDK with
authentication, health checks, and comprehensive validation endpoints.

USAGE:
  # Development
  python3 examples/flask_api_server.py

  # Production with Gunicorn
  export GUARDLY_API_KEYS="key1,key2,key3"
  gunicorn --workers 4 --bind 0.0.0.0:5000 \
    "examples.flask_api_server:create_app()"

ENVIRONMENT VARIABLES:
  GUARDLY_API_KEYS      Comma-separated API keys (required)
  GUARDLY_PORT          Port to listen on (default: 5000)
  GUARDLY_HOST          Host to bind to (default: 0.0.0.0)
  GUARDLY_DEBUG         Enable Flask debug mode (default: false)
  HG_LOG_LEVEL          Logging level: DEBUG, INFO, WARNING, ERROR (default: INFO)
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, request, jsonify
from frontend.app import app as default_app

# ============================================================================
# LOGGING SETUP
# ============================================================================

log_level = os.getenv('HG_LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

PORT = int(os.getenv('GUARDLY_PORT', '5000'))
HOST = os.getenv('GUARDLY_HOST', '0.0.0.0')
DEBUG = os.getenv('GUARDLY_DEBUG', '').lower() == 'true'

# API Key authentication
API_KEYS = set(
    key.strip() for key in os.getenv('GUARDLY_API_KEYS', '').split(',')
    if key.strip()
)

if not API_KEYS or not next(iter(API_KEYS)):
    logger.warning('⚠️  No API keys configured. Set GUARDLY_API_KEYS environment variable.')
    logger.warning('   Example: export GUARDLY_API_KEYS="key1,key2,key3"')

# ============================================================================
# APPLICATION SETUP
# ============================================================================

app = default_app

@app.before_request
def log_request():
    """Log incoming requests."""
    logger.debug(f'{request.method} {request.path}')

@app.after_request
def log_response(response):
    """Log response status."""
    logger.debug(f'Response: {response.status_code}')
    return response

# ============================================================================
# STARTUP & WARMUP
# ============================================================================

@app.before_request
def warmup_models():
    """Pre-load models on first request for faster cold-start."""
    if not hasattr(warmup_models, 'done'):
        logger.info('🔥 Pre-loading validation models (first request, ~6-8 seconds)...')
        try:
            from frontend.service import GuardService
            service = GuardService.get_instance()
            
            # Pre-load default policy guard
            guard = service.get_guard('default')
            
            logger.info('✅ Models pre-loaded successfully')
            warmup_models.done = True
        except Exception as e:
            logger.error(f'⚠️  Model pre-loading failed: {e}')
            warmup_models.done = True

# ============================================================================
# INFO ENDPOINTS
# ============================================================================

@app.route('/')
def root():
    """API root - documentation link."""
    return jsonify({
        'message': 'GuardlyAI REST API',
        'version': '1.0.0',
        'docs': 'http://localhost:5000/docs',
        'health': 'http://localhost:5000/health',
        'endpoints': {
            'validate': 'POST /validate',
            'batch': 'POST /validate/batch',
            'health': 'GET /health',
            'version': 'GET /version',
            'policies': 'GET /config/policies'
        }
    }), 200

@app.route('/docs')
def docs():
    """Documentation redirect."""
    return jsonify({
        'docs_url': 'https://github.com/guardly/guardly-ai/blob/main/docs/REST_API.md',
        'deployment': 'https://github.com/guardly/guardly-ai/blob/main/docs/DEPLOYMENT.md',
        'node_sdk': 'https://github.com/guardly/guardly-ai/blob/main/docs/NODE_SDK_USAGE.md'
    }), 200

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return jsonify({
        'error': 'NOT_FOUND',
        'message': f'Endpoint not found: {request.path}',
        'status_code': 404
    }), 404

@app.errorhandler(405)
def method_not_allowed(error):
    """Handle 405 errors."""
    return jsonify({
        'error': 'METHOD_NOT_ALLOWED',
        'message': f'Method {request.method} not allowed for {request.path}',
        'status_code': 405
    }), 405

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f'Internal server error: {error}')
    return jsonify({
        'error': 'INTERNAL_ERROR',
        'message': 'Internal server error',
        'status_code': 500
    }), 500

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Run the Flask development server."""
    if not API_KEYS:
        logger.warning('⚠️  No API keys set! API will reject all authenticated requests.')
        logger.warning('   Set GUARDLY_API_KEYS before running in production.')
    
    logger.info(f'🚀 Starting GuardlyAI API Server')
    logger.info(f'   Host: {HOST}')
    logger.info(f'   Port: {PORT}')
    logger.info(f'   Debug: {DEBUG}')
    logger.info(f'   Log level: {log_level}')
    logger.info(f'   API keys configured: {len(API_KEYS)}')
    logger.info('')
    logger.info('📝 Endpoints:')
    logger.info(f'   POST   /validate         - Single validation')
    logger.info(f'   POST   /validate/batch   - Batch validation')
    logger.info(f'   GET    /health           - Health check')
    logger.info(f'   GET    /version          - Version info')
    logger.info(f'   GET    /config/policies  - List policies')
    logger.info('')
    logger.info(f'🌐 Access at: http://{HOST}:{PORT}')
    logger.info(f'📚 Docs at: http://{HOST}:{PORT}/docs')
    logger.info('')
    
    app.run(
        host=HOST,
        port=PORT,
        debug=DEBUG,
        use_reloader=DEBUG
    )

if __name__ == '__main__':
    main()
