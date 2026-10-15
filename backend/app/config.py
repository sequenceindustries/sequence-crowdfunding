import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg:///crowdfund?host=/tmp&port=5433&user=postgres"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV") == "production"
    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.abspath("private_uploads"))
    MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "15"))
    MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024
    FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")
    RATELIMIT_STORAGE_URI = os.environ.get("REDIS_URL", "memory://")
    RATELIMIT_ENABLED = True
    AI_PROVIDER = os.environ.get("AI_PROVIDER", "mock")
    PAYMENT_PROVIDER = os.environ.get("PAYMENT_PROVIDER", "mock")
    # Fee is configuration, not code. The service it buys is deliberately unset
    # until the business confirms which of the four interpretations applies.
    PITCH_DECK_FEE_ZAR_CENTS = int(os.environ.get("PITCH_DECK_FEE_ZAR_CENTS", "50000"))
    # Provisional decision (reversible by config): the fee buys upload + analysis + improvement report
    # for one deck. Valid values: unconfigured | upload | analysis | package.
    PITCH_DECK_FEE_SERVICE = os.environ.get("PITCH_DECK_FEE_SERVICE", "package")
    # Charging stays off until this is set AND a payment mode other than "off" is active.
    PITCH_DECK_FEE_CHARGING_ENABLED = os.environ.get("PITCH_DECK_FEE_CHARGING_ENABLED", "false") == "true"
    MAIL_PROVIDER = os.environ.get("MAIL_PROVIDER", "outbox")
    # off | simulated | live. "simulated" needs a simulated provider, "live" needs a live one.
    CONTRIBUTIONS_MODE = os.environ.get("CONTRIBUTIONS_MODE", "off")
    PAYMENT_WEBHOOK_SECRET = os.environ.get("PAYMENT_WEBHOOK_SECRET", "")
    CONTRIBUTION_MIN_CENTS = 2000        # R20
    CONTRIBUTION_MAX_CENTS = 5_000_000   # R50 000 per contribution
    ENABLED_FUNDING_MODELS = ["donation", "reward", "business_support"]


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL", "postgresql+psycopg:///crowdfund_test?host=/tmp&port=5433&user=postgres"
    )
    RATELIMIT_STORAGE_URI = "memory://"
    RATELIMIT_ENABLED = False
    SECRET_KEY = "test-key"
    PAYMENT_WEBHOOK_SECRET = "test-webhook-secret"
