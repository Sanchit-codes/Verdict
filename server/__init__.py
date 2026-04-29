"""Flask application factory and initialization."""

from typing import Any

from flask import Flask

from .config import Config, get_config
from .middleware import setup_cors, setup_error_handlers, setup_logging
from .routes import create_routes, preload_models


def create_app(config: Any = None) -> Flask:
    """Create and configure the Flask application.

    Args:
        config: Optional Config instance. If None, uses environment-based config.

    Returns:
        Configured Flask app ready to serve requests.
    """
    # Load config
    if config is None:
        config = get_config()

    # Setup logging
    setup_logging(log_level=config.GUARD_LOG_LEVEL)

    # Create Flask app
    app = Flask(__name__)
    app.config.from_object(config)

    # Setup middleware
    setup_error_handlers(app)
    setup_cors(app)

    # Register API routes
    api_bp = create_routes(app, config)
    app.register_blueprint(api_bp)

    # Start background model preload
    preload_models(config)

    return app
