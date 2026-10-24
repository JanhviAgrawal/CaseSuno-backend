"""
CASE SUNO backend settings.

Works in three environments with the same file:
  * Local development      -> .env file (see .env.example)
  * Render (production)    -> environment variables set in the Render dashboard / render.yaml
  * Docker compose         -> docker-compose.yml

Optional services (Redis, Celery worker, S3, ClamAV, Sentry) are *optional*:
if their settings are empty the app falls back to safe built-in behaviour
(local-memory cache, background jobs run inline, uploads disabled).
"""

from pathlib import Path
import os

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)

environ.Env.read_env(BASE_DIR / ".env")


# --------------------------------------------------
# Core
# --------------------------------------------------
SECRET_KEY = env("SECRET_KEY", default="")
DEBUG = env("DEBUG")

if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-secret-key-change-me"
    else:
        raise RuntimeError("SECRET_KEY environment variable must be set in production.")

# Public website (used for links in e-mails and tracking URLs)
SITE_URL = env("SITE_URL", default="https://casesuno.in").rstrip("/")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# Render injects the service hostname automatically (e.g. casesuno-api.onrender.com)
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=[
        "https://casesuno.in",
        "https://www.casesuno.in",
        "http://localhost:3000",
    ],
)
CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=["https://casesuno.in", "https://www.casesuno.in"],
)
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

# Shared secret between the Next.js website server and this API.
# When set, every /api/web/ request must carry the header  X-Website-Key: <value>.
WEBSITE_API_KEY = env("WEBSITE_API_KEY", default="")

# Optional: where new-enquiry alerts are e-mailed (comma separated)
ADMIN_NOTIFY_EMAILS = env.list("ADMIN_NOTIFY_EMAILS", default=[])

# WhatsApp support number used in customer-facing metadata
SUPPORT_WHATSAPP_NUMBER = env("SUPPORT_WHATSAPP_NUMBER", default="918000784778")


# --------------------------------------------------
# Applications
# --------------------------------------------------
INSTALLED_APPS = [
    "corsheaders",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Django REST Framework
    "rest_framework",
    # CASE SUNO apps
    "accounts",
    "customer_requirements",
    "proposals",
    "payments",
    "matters",
    "professionals",
    "documents",
    "tasks",
    "audit",
    "website",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --------------------------------------------------
# Database
#   Render / Heroku style:  DATABASE_URL=postgres://user:pass@host:5432/db
#   Or individual DB_* variables (local / docker)
# --------------------------------------------------
if env("DATABASE_URL", default=""):
    DATABASES = {"default": env.db("DATABASE_URL")}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DB_NAME", default="case_suno_db"),
            "USER": env("DB_USER", default="postgres"),
            "PASSWORD": env("DB_PASSWORD", default=""),
            "HOST": env("DB_HOST", default="127.0.0.1"),
            "PORT": env.int("DB_PORT", default=5432),
        }
    }

DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True


# --------------------------------------------------
# Passwords
# --------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --------------------------------------------------
# Internationalization
# --------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True


# --------------------------------------------------
# Static files (Django admin) served by WhiteNoise
# --------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
            if not DEBUG
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --------------------------------------------------
# Security (production behind Render's HTTPS proxy)
# --------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"


# --------------------------------------------------
# REST Framework
# --------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "common.permissions.admin_auth.AdminSessionAuthentication",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("ANON_THROTTLE_RATE", default="5/minute"),
        # Website (public) endpoints — keyed by the real visitor IP forwarded by the website server
        "web_enquiry": "6/10m",
        "web_lookup": "10/10m",
        "web_message": "15/10m",
        "web_order": "10/10m",
        "web_login": "8/15m",
    },
}


# --------------------------------------------------
# Email
# --------------------------------------------------
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=15)
DEFAULT_FROM_EMAIL = env(
    "DEFAULT_FROM_EMAIL",
    default="CASE SUNO <no-reply@casesuno.in>",
)

# SMTP selected but no mailbox credentials yet -> log e-mails instead of failing
if EMAIL_BACKEND.endswith("smtp.EmailBackend") and not EMAIL_HOST_USER:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"


# --------------------------------------------------
# Razorpay
# --------------------------------------------------
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", default="")
RAZORPAY_WEBHOOK_SECRET = env("RAZORPAY_WEBHOOK_SECRET", default="")


# --------------------------------------------------
# Private S3-compatible document storage (optional)
# --------------------------------------------------
S3_ENDPOINT = env("S3_ENDPOINT", default="")
S3_KEY = env("S3_KEY", default="")
S3_SECRET = env("S3_SECRET", default="")
S3_BUCKET = env("S3_BUCKET", default="")
S3_REGION = env("S3_REGION", default="us-east-1")

# ClamAV antivirus service (optional)
CLAMAV_HOST = env("CLAMAV_HOST", default="127.0.0.1")
CLAMAV_PORT = env.int("CLAMAV_PORT", default=3310)


# --------------------------------------------------
# Redis cache (optional) — falls back to in-process memory
# --------------------------------------------------
REDIS_CACHE_URL = env("DJANGO_CACHE_REDIS_URL", default="") or env("REDIS_URL", default="")

if REDIS_CACHE_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_CACHE_URL,
        },
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "casesuno-default",
        },
    }


# --------------------------------------------------
# Celery (optional) — without a broker, tasks run inline
# --------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="")

if not CELERY_BROKER_URL:
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = False
    CELERY_BROKER_URL = "memory://"
    CELERY_RESULT_BACKEND = None

CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = USE_TZ
CELERY_TASK_SOFT_TIME_LIMIT = 240
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_IGNORE_RESULT = True
CELERY_BEAT_SCHEDULE = {}


# --------------------------------------------------
# Logging (stdout, picked up by Render logs)
# --------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
    },
}


# --------------------------------------------------
# Sentry Error Monitoring (optional)
# --------------------------------------------------
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            integrations=[DjangoIntegration()],
            traces_sample_rate=0.2,
            send_default_pii=False,
        )
    except ImportError:
        pass


# --------------------------------------------------
# Structured JSON logging helpers (Build Plan Section 13)
# --------------------------------------------------
try:
    import structlog

    def filter_sensitive_log_data(logger, method_name, event_dict):
        """Never log OTPs, passwords, full mobile numbers, or secret keys."""
        for key in ("otp", "password", "token", "key_secret", "secret", "raw_token"):
            if key in event_dict:
                event_dict[key] = "[REDACTED]"
        if "mobile" in event_dict and isinstance(event_dict["mobile"], str):
            mob = event_dict["mobile"]
            if len(mob) >= 4:
                event_dict["mobile"] = "*" * (len(mob) - 4) + mob[-4:]
        return event_dict

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            filter_sensitive_log_data,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
except ImportError:
    pass
