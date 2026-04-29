"""Configuration management for the Flask API server."""

import os
from pathlib import Path


class Config:
    """Base configuration class."""

    # Flask config
    DEBUG: bool = False
    TESTING: bool = False
    JSON_SORT_KEYS: bool = False
    JSONIFY_PRETTYPRINT_REGULAR: bool = False

    # Server config
    SERVER_VERSION: str = "1.0.0"
    PORT: int = int(os.getenv("PORT", "5000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")
    WORKERS: int = int(os.getenv("WORKERS", "1"))
    CORS_ORIGIN: str = os.getenv("CORS_ORIGIN", "http://localhost:3000")

    # HallucinationGuard config
    DEFAULT_POLICY: str = os.getenv("HG_DEFAULT_POLICY", "default")
    GUARD_LOG_LEVEL: str = os.getenv("HG_LOG_LEVEL", "INFO")
    ENABLE_TRACE_EXPORT: bool = os.getenv("HG_ENABLE_TRACE_EXPORT", "false").lower() == "true"
    TRACE_DIR: Path = Path(os.getenv("HG_TRACE_DIR", "~/.verdict/traces")).expanduser()

    # Model loading config
    PRELOAD_MODELS: bool = os.getenv("HG_PRELOAD_MODELS", "true").lower() == "true"
    MODEL_WARMUP_TIMEOUT_SECS: int = int(os.getenv("HG_WARMUP_TIMEOUT", "60"))

    # Batch processing config
    MAX_BATCH_SIZE: int = 100
    MAX_PARALLEL_VALIDATIONS: int = 10
    BATCH_TIMEOUT_SECS: float = 60.0

    # Validation config
    DEFAULT_DOMAIN: str = "general"
    ENABLE_ARMORIQ: bool = os.getenv("HG_ENABLE_ARMORIQ", "false").lower() == "true"

    # Gemini LLM config
    GEMINI_API_KEY: str | None = os.getenv("GOOGLE_API_KEY")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_TEMPERATURE: float = float(os.getenv("GEMINI_TEMPERATURE", "0.7"))
    GEMINI_MAX_TOKENS: int = int(os.getenv("GEMINI_MAX_TOKENS", "1024"))

    # Observability config
    REQUEST_LOGGING_ENABLED: bool = True
    LATENCY_TRACKING_ENABLED: bool = True

    @classmethod
    def get_policy_path(cls, policy_name: str) -> Path | None:
        """Get full path to policy file."""
        policy_dir = Path(__file__).parent.parent / "policies"
        policy_file = policy_dir / f"{policy_name}.yaml"
        return policy_file if policy_file.exists() else None

    @classmethod
    def get_available_policies(cls) -> list[str]:
        """Get list of available policies."""
        policy_dir = Path(__file__).parent.parent / "policies"
        if not policy_dir.exists():
            return []
        return [f.stem for f in policy_dir.glob("*.yaml")]


class DevelopmentConfig(Config):
    """Development configuration."""

    DEBUG = True
    GUARD_LOG_LEVEL = "DEBUG"
    PRELOAD_MODELS = True
    REQUEST_LOGGING_ENABLED = True


class ProductionConfig(Config):
    """Production configuration."""

    DEBUG = False
    WORKERS = int(os.getenv("WORKERS", "4"))
    ENABLE_TRACE_EXPORT = True


class TestingConfig(Config):
    """Testing configuration."""

    TESTING = True
    DEBUG = True
    PRELOAD_MODELS = False
    GUARD_LOG_LEVEL = "DEBUG"
    MODEL_WARMUP_TIMEOUT_SECS = 5


def get_config() -> Config:
    """Get config based on environment."""
    env = os.getenv("FLASK_ENV", "development").lower()
    if env == "production":
        return ProductionConfig()
    elif env == "testing":
        return TestingConfig()
    else:
        return DevelopmentConfig()
