#!/usr/bin/env python3
"""Entry point script for running the HallucinationGuard Flask API server.

Usage:
    python server/run.py                    # Run with defaults (port 5000)
    PORT=3000 python server/run.py          # Run on port 3000
    FLASK_ENV=production python server/run.py  # Run in production mode
"""

import os
import sys
from pathlib import Path

# Add parent directory to path so we can import server and verdict
sys.path.insert(0, str(Path(__file__).parent.parent))

from server import create_app
from server.config import get_config

if __name__ == "__main__":
    config = get_config()

    # Create Flask app
    app = create_app(config)

    # Run server
    print("🚀 Starting HallucinationGuard API Server")
    print(f"   Version: {config.SERVER_VERSION}")
    print(f"   Environment: {os.getenv('FLASK_ENV', 'development').upper()}")
    print(f"   Policy: {config.DEFAULT_POLICY}")
    print(f"   Models preload: {config.PRELOAD_MODELS}")
    print(f"   Listening on {config.HOST}:{config.PORT}")
    print(f"   CORS Origin: {config.CORS_ORIGIN}")
    print(f"\n   API Docs: http://{config.HOST}:{config.PORT}/api/docs")
    print(f"   Health: http://{config.HOST}:{config.PORT}/api/health")
    print()

    # Run Flask app
    app.run(
        host=config.HOST,
        port=5500,
        debug=config.DEBUG,
        use_reloader=False,  # Preserve model cache
    )
