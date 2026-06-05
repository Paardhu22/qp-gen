from pathlib import Path
import os

import dj_database_url
from corsheaders.defaults import default_headers
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env", override=True)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "unsafe-dev-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"

allowed_hosts = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
ALLOWED_HOSTS = [host.strip() for host in allowed_hosts if host.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "corsheaders",
    "pgvector.django",
    "apps.accounts",
    "apps.documents",
    "apps.generation",
    "apps.projects",
    "apps.common",
    "apps.question_generation",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

APPEND_SLASH = False

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASE_URL = os.environ.get("DATABASE_URL")

# Require a PostgreSQL DATABASE_URL (Neon) — do not fall back to SQLite.
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is required. Add it to backend/.env and restart the app."
    )

# Parse the DATABASE_URL and require SSL (Neon provides sslmode=require).
DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        ssl_require=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
AOS_PUBLIC_MEDIA_BASE_URL = os.environ.get("AOS_PUBLIC_MEDIA_BASE_URL", "").rstrip("/")
PDF_IMAGE_MAX_CAPTIONS = int(os.environ.get("PDF_IMAGE_MAX_CAPTIONS", "40"))
PDF_IMAGE_MIN_BYTES = int(os.environ.get("PDF_IMAGE_MIN_BYTES", "8192"))
PDF_IMAGE_MIN_DIMENSION = int(os.environ.get("PDF_IMAGE_MIN_DIMENSION", "96"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.common.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
}

JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TTL_DAYS = int(os.environ.get("JWT_ACCESS_TTL_DAYS", "7"))
JWT_REFRESH_TTL_DAYS = int(os.environ.get("JWT_REFRESH_TTL_DAYS", "30"))
JWT_ISSUER = os.environ.get("JWT_ISSUER", "qp-gen")

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")
CORS_ALLOWED_ORIGINS = [FRONTEND_URL]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = list(default_headers) + ["X-CSRFToken"]

CSRF_TRUSTED_ORIGINS = [FRONTEND_URL]
SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
CSRF_COOKIE_SECURE = os.environ.get("CSRF_COOKIE_SECURE", "false").lower() == "true"
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# ---------------------------------------------------------------------------
# Email — password-reset + welcome emails (Cluster A.1).
#
# Default backend is the console writer so local development surfaces every
# email in the runserver log without needing real SMTP credentials. Override
# `EMAIL_BACKEND` for production (typical values:
# `django.core.mail.backends.smtp.EmailBackend` for SMTP/SendGrid/SES SMTP
# relay; or a third-party library backend like `anymail.backends.ses`).
# The reset URL is built from `FRONTEND_URL` so the host always matches the
# deployed origin and never leaks `localhost:3000` into production emails.
# ---------------------------------------------------------------------------
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "false").lower() == "true"
EMAIL_TIMEOUT = int(os.environ.get("EMAIL_TIMEOUT", "20"))
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", "qp-gen <no-reply@qp-gen.local>"
)
PASSWORD_RESET_TIMEOUT = int(
    os.environ.get("PASSWORD_RESET_TIMEOUT_SECONDS", str(60 * 60))
)  # 1 hour default
PASSWORD_RESET_URL_PATH = os.environ.get(
    "PASSWORD_RESET_URL_PATH", "/reset-password"
)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
if not OPENAI_API_KEY:
    raise RuntimeError(
        "OPENAI_API_KEY is required. Add it to backend/.env and restart the server.\n"
        "Get your key at https://platform.openai.com/api-keys"
    )
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5-mini")
QG_NEW_ENGINE_ENABLED = os.environ.get("QG_NEW_ENGINE_ENABLED", "false").lower() == "true"
OPENAI_EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
# Vision captioning during PDF ingestion runs against this model. gpt-5-mini
# (the generation default) is a reasoning model and bills ~10 s of internal
# reasoning per vision call. gpt-4o-mini is fast but bills ~2800 input tokens
# per image regardless of detail level (OpenAI's billing model for "mini"
# vision), which saturates the 200k TPM Tier 1 budget after ~5 concurrent
# calls. gpt-4o with detail="low" bills ~85 tokens per image and finishes in
# ~1.2 s, so 22 parallel captioning calls fit comfortably within TPM and
# total ingestion drops from ~250 s → ~5 s.
OPENAI_VISION_MODEL = os.environ.get("OPENAI_VISION_MODEL", "gpt-4o")
# Max concurrent vision-API requests during image captioning. The OpenAI Tier 1
# rate limits for gpt-4o-mini comfortably absorb 8 concurrent requests; bigger
# tiers can push this higher. Combined with the 22-image trignometry.pdf load
# this brings total ingestion from ~250 s to <30 s.
PDF_IMAGE_CAPTION_CONCURRENCY = int(
    os.environ.get("PDF_IMAGE_CAPTION_CONCURRENCY", "8")
)

# Cache configuration for improved API performance
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "qp-gen-cache",
        "OPTIONS": {
            "MAX_ENTRIES": 1000,
        },
        "TIMEOUT": 300,  # 5 minutes default
    }
}

# Database connection pooling for faster response times
DATABASES["default"]["CONN_MAX_AGE"] = 600  # Keep connections alive for 10 minutes
DATABASES["default"]["OPTIONS"] = {
    "connect_timeout": 10,
    "application_name": "qp-gen",
}
