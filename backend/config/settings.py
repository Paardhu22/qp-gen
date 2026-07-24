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
    "apps.storage",
    "storages",
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

# Require a PostgreSQL DATABASE_URL — do not fall back to SQLite unless running tests.
import sys
if "test" in sys.argv:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
        }
    }
else:
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is required. Add it to backend/.env and restart the app."
        )

    # Parse the DATABASE_URL. SSL is optional for local PostgreSQL deployments on EC2.
    DATABASE_SSL_REQUIRE = os.environ.get("DATABASE_SSL_REQUIRE", "false").lower() == "true"
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=DATABASE_SSL_REQUIRE,
        )
    }

    if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
        DATABASES["default"]["OPTIONS"] = {
            "timeout": 20,
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


def _int_env(
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw_value = os.environ.get(name)
    try:
        value = int(raw_value) if raw_value is not None else default
    except ValueError:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


STATIC_URL = "static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
AOS_PUBLIC_MEDIA_BASE_URL = os.environ.get("AOS_PUBLIC_MEDIA_BASE_URL", "").rstrip("/")
PDF_IMAGE_MAX_CAPTIONS = _int_env("PDF_IMAGE_MAX_CAPTIONS", 40, minimum=0)
PDF_IMAGE_MIN_BYTES = _int_env("PDF_IMAGE_MIN_BYTES", 8192, minimum=0)
PDF_IMAGE_MIN_DIMENSION = _int_env("PDF_IMAGE_MIN_DIMENSION", 96, minimum=0)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "httpx": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "httpcore": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.common.authentication.CognitoJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "apps.common.permissions.IsApprovedOrAdmin",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
}

# Upload size limits. nginx caps the request body at 100M
# (client_max_body_size on api.hsatedu.in); these keep Django from being a
# lower ceiling. For multipart file uploads these are not the active limiter
# (file bytes are streamed and not counted against DATA_UPLOAD_MAX_MEMORY_SIZE),
# but they are set explicitly so any future raw-body/JSON/base64 upload path is
# not silently capped at Django's 2.5MB default.
DATA_UPLOAD_MAX_MEMORY_SIZE = 104857600   # 100 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 104857600   # 100 MB

# AWS Cognito Configuration
AWS_COGNITO_REGION = os.environ.get("AWS_COGNITO_REGION", "ap-south-1")
AWS_COGNITO_USER_POOL_ID = os.environ.get("AWS_COGNITO_USER_POOL_ID", "ap-south-1_zHrjkaeQy")
# NO hard-coded default: the prior literal "…occdoLk7ivf" contained an ℓ/1 typo
# (console value ends "…occdo1k7ivf") which silently broke the access-token
# `client_id` / ID-token `aud` check and rejected every token. The value must
# also be the NEW *no-secret* app client (see FIX_REPORT.md → ACTION REQUIRED).
# Unset ⇒ the validator fails closed (rejects all tokens) instead of trusting a
# wrong client. Must match NEXT_PUBLIC_AWS_COGNITO_APP_CLIENT_ID on the frontend.
AWS_COGNITO_APP_CLIENT_ID = os.environ.get("AWS_COGNITO_APP_CLIENT_ID", "")

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
# ─── Single source of truth for the model ──────────────────────────────────
# ─── Explicit per-stage model configuration ────────────────────────────────
# The backend owns model selection; the frontend NEVER names a model. Each
# generation stage has its OWN explicit model so no stage silently inherits
# another's env override. In particular, POOL_MODEL / REVIEW_MODEL /
# ANSWER_MODEL do NOT fall back to OPENAI_MODEL — a deployment that set
# `OPENAI_MODEL=gpt-4o` (a 30k-TPM model) must not drag Model 1's whole-chapter
# request into that ceiling. Defaults are gpt-4.1-mini: a large-context, high-
# TPM model that comfortably fits a per-chapter prompt.
#
#   POOL_MODEL      — Model 1 (pool generation) + image-spec proposal
#   REVIEW_MODEL    — Model 2 (paper assembly review)
#   ANSWER_MODEL    — answer-key + answer-script generation
#   OPENAI_IMAGE_MODEL     — diagram image generation (gpt-image-1)
#   OPENAI_EMBEDDING_MODEL — retrieval embeddings (text-embedding-3-small)
#   OPENAI_MODEL    — legacy/blueprint fallback ONLY; nothing above inherits it.
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
QG_NEW_ENGINE_ENABLED = os.environ.get("QG_NEW_ENGINE_ENABLED", "false").lower() == "true"
OPENAI_EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
# Retained for the (now-optional) vision-caption helper; ingestion no longer
# calls it (no GPT calls during ingestion — see services.document_service).
OPENAI_VISION_MODEL = os.environ.get("OPENAI_VISION_MODEL", "gpt-4.1-mini")

# ─── Question Pool architecture ────────────────────────────────────────────
# Model 1 (pool generation). Explicit default, independent of OPENAI_MODEL.
POOL_MODEL = os.environ.get("POOL_MODEL", "gpt-4.1-mini")
# Model 2 (paper assembly / review) and answer generation. Explicit defaults.
REVIEW_MODEL = os.environ.get("REVIEW_MODEL", "gpt-4.1-mini")
ANSWER_MODEL = os.environ.get("ANSWER_MODEL", "gpt-4.1-mini")

# ─── Per-chapter Model 1 execution (TPM safety) ─────────────────────────────
# Model 1 processes ONE chapter per request, never the whole upload. These
# knobs bound how large a single prompt can get and how many run at once so the
# organisation's tokens-per-minute ceiling is never exceeded.
#
#   POOL_CHAPTER_TOKEN_THRESHOLD — a detected chapter larger than this (input
#     tokens) is split into semantic sections before generation. Keep it well
#     under the smallest model's TPM so a single request always fits.
#   POOL_MAX_CONCURRENCY — process-wide cap on concurrent Model 1 API requests
#     (a semaphore in services.pool.model1). concurrency × threshold must stay
#     under TPM.
#   POOL_CHAPTER_CONCURRENCY — how many chapters generate in parallel.
#   POOL_MIN_QUESTIONS_PER_CHAPTER — floor so a chapter's slice of the pool is
#     still a usable spread of types when many chapters share one paper.
POOL_CHAPTER_TOKEN_THRESHOLD = _int_env(
    "POOL_CHAPTER_TOKEN_THRESHOLD", 20_000, minimum=4_000, maximum=100_000
)
POOL_MAX_CONCURRENCY = _int_env("POOL_MAX_CONCURRENCY", 4, minimum=1, maximum=16)
POOL_CHAPTER_CONCURRENCY = _int_env(
    "POOL_CHAPTER_CONCURRENCY", 3, minimum=1, maximum=16
)
POOL_MIN_QUESTIONS_PER_CHAPTER = _int_env(
    "POOL_MIN_QUESTIONS_PER_CHAPTER", 12, minimum=1, maximum=200
)

# Whole-chapter Markdown handed to Model 1. ~240k chars ≈ 60k tokens, far more
# than any single CBSE chapter; the cap only exists to stop somebody feeding a
# complete textbook through as one "chapter".
CHAPTER_MD_MAX_CHARS = _int_env(
    "CHAPTER_MD_MAX_CHARS", 240_000, minimum=10_000, maximum=2_000_000
)

# How image-bearing questions are produced:
#   generate — synthesise new diagrams with OPENAI_IMAGE_MODEL
#   reuse    — write questions about figures extracted from the uploaded PDF
#   hybrid   — reuse the chapter's own figures first, synthesise the remainder (default)
#
# `generate` is the most expensive option by a wide margin (see
# IMAGE_COST_USD_PER_IMAGE) and an AI-drawn circuit or ray diagram can be
# subtly wrong, so every synthesised question is tagged for teacher review.
# `hybrid` keeps images available where they help without forcing every image
# question through the image-generation endpoint.
IMAGE_QUESTION_STRATEGY = os.environ.get("IMAGE_QUESTION_STRATEGY", "hybrid").strip().lower()

# Hard upper cap on image questions per pool. The pipeline still computes a
# smaller contextual budget from the paper/subject so images appear only where
# they are useful.
IMAGE_QUESTIONS_PER_POOL = _int_env(
    "IMAGE_QUESTIONS_PER_POOL", 8, minimum=0, maximum=40
)
OPENAI_IMAGE_CONCURRENCY = _int_env("OPENAI_IMAGE_CONCURRENCY", 1, minimum=1, maximum=4)

OPENAI_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")
OPENAI_IMAGE_SIZE = os.environ.get("OPENAI_IMAGE_SIZE", "1024x1024")
# Cheapest suitable quality tier for educational diagrams. gpt-image-1 accepts
# low|medium|high; "low" is ~4-8x cheaper than "high" and remains legible for
# schematic figures (ray diagrams, circuits). Bump to "medium" via env if a
# subject needs finer detail.
OPENAI_IMAGE_QUALITY = os.environ.get("OPENAI_IMAGE_QUALITY", "low").strip().lower()

# Used only to report an estimated spend on the SSE `pool` event so the cost of
# a generation is visible in the UI rather than discovered on the invoice.
IMAGE_COST_USD_PER_IMAGE = float(os.environ.get("IMAGE_COST_USD_PER_IMAGE", "0.04"))

# ---------------------------------------------------------------------------
# Cache — Elasticache-ready (statelessness pass P3).
#
# REDIS_URL set   → shared Redis cache (django.core.cache.backends.redis,
#                   needs the `redis` package). Required for multi-instance
#                   deployments: the per-user read caches in
#                   apps/projects/views.py are invalidated on write, and
#                   that invalidation only works if all instances share one
#                   cache. Elasticache: redis://<primary-endpoint>:6379/0
#                   (rediss:// when in-transit encryption is on).
# REDIS_URL unset → per-process LocMemCache, exactly today's behaviour —
#                   fine for local dev and a single-instance box.
#
# If REDIS_URL is set but the redis package is missing we WARN and fall
# back to LocMem rather than crash the boot (degrade-gracefully rule).
# ---------------------------------------------------------------------------
def build_cache_config(redis_url: str, redis_importable: bool | None = None) -> dict:
    """Pure helper so tests can assert backend selection without reimporting
    settings. ``redis_importable=None`` autodetects the redis package."""
    if redis_url:
        if redis_importable is None:
            try:
                import redis  # noqa: F401
                redis_importable = True
            except ImportError:
                redis_importable = False
        if redis_importable:
            return {
                "default": {
                    "BACKEND": "django.core.cache.backends.redis.RedisCache",
                    "LOCATION": redis_url,
                    "KEY_PREFIX": "qpgen",
                    "TIMEOUT": 300,  # 5 minutes default
                }
            }
        import logging as _logging

        _logging.getLogger(__name__).warning(
            "REDIS_URL is set but the `redis` package is not installed; "
            "falling back to per-process LocMemCache. "
            "`pip install redis` to enable the shared cache."
        )
    return {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "qp-gen-cache",
            "OPTIONS": {
                "MAX_ENTRIES": 1000,
            },
            "TIMEOUT": 300,  # 5 minutes default
        }
    }


REDIS_URL = os.environ.get("REDIS_URL", "").strip()
CACHES = build_cache_config(REDIS_URL)

# Database connection pooling for faster response times
if "test" not in sys.argv and "sqlite" not in DATABASES["default"].get("ENGINE", ""):
    DATABASES["default"]["CONN_MAX_AGE"] = 600  # Keep connections alive for 10 minutes
    DATABASES["default"]["OPTIONS"] = {
        "connect_timeout": 10,
        "application_name": "qp-gen",
    }

# ---------------------------------------------------------------------------
# Optional S3/MinIO storage configuration. When `AWS_STORAGE_BUCKET_NAME` is
# set the project will use `django-storages` S3Boto3 backend as the
# `DEFAULT_FILE_STORAGE`. For local development you can set
# `AWS_S3_ENDPOINT_URL` to a MinIO instance.
# ---------------------------------------------------------------------------
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID") or None
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY") or None
AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME", "")
AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME", "ap-south-1")
# NOTE: botocore rejects an empty string endpoint_url with "Invalid endpoint:".
# django-storages passes settings.AWS_S3_ENDPOINT_URL straight through, so we
# must collapse "" → None here. None tells boto3 to use the default regional
# AWS endpoint. Set to e.g. http://localhost:9000 for MinIO.
AWS_S3_ENDPOINT_URL = os.environ.get("AWS_S3_ENDPOINT_URL", "") or None
AWS_S3_SIGNATURE_VERSION = os.environ.get("AWS_S3_SIGNATURE_VERSION", "s3v4")
AWS_S3_ADDRESSING_STYLE = os.environ.get("AWS_S3_ADDRESSING_STYLE", "auto")
AWS_S3_USE_SSL = os.environ.get("AWS_S3_USE_SSL", "true").lower() == "true"
AWS_QUERYSTRING_EXPIRE = int(os.environ.get("AWS_QUERYSTRING_EXPIRE", "3600"))

if AWS_STORAGE_BUCKET_NAME:
    DEFAULT_FILE_STORAGE = "storages.backends.s3boto3.S3Boto3Storage"
    # Allow overriding the public media base if using a CDN or custom domain
    # e.g. set AOS_PUBLIC_MEDIA_BASE_URL=https://cdn.example.com
    # The storage backend will still generate URLs via `default_storage.url()`

# ---------------------------------------------------------------------------
# HSAT shared-textbook bucket — read-only source PDFs consumed by
# services/s3_client.py (NOT django-storages). This bucket can live in a
# DIFFERENT region than the uploads bucket above:
#   uploads  → AWS_STORAGE_BUCKET_NAME @ AWS_S3_REGION_NAME  (e.g. qp-gen-pdfs / ap-southeast-2)
#   HSAT     → HSAT_S3_BUCKET          @ HSAT_S3_REGION       (e.g. storagetank-hsat / ap-south-1)
# A boto3/SigV4 request or presigned URL signed for the WRONG region fails with
# 403 AuthorizationHeaderMalformed, so each client must sign for its own bucket's
# region. When HSAT_S3_* are unset they fall back to the uploads bucket/region so
# single-bucket (or local MinIO) deployments keep working unchanged.
# ---------------------------------------------------------------------------
HSAT_S3_BUCKET = os.environ.get("HSAT_S3_BUCKET", "") or AWS_STORAGE_BUCKET_NAME
HSAT_S3_REGION = os.environ.get("HSAT_S3_REGION", "") or AWS_S3_REGION_NAME

# ---------------------------------------------------------------------------
# Paper.content read source (statelessness pass P2).
#
# "db" (default): Paper content is read from the authoritative DB column —
#                 byte-for-byte today's behaviour.
# "s3":           reads try the dual-written paper-content/{userId}/{paperId}
#                 .json object first and fall back to the DB column on ANY
#                 miss or error.
#
# Writes ALWAYS dual-write (DB first — authoritative — then best-effort S3
# mirror). Flip this to "s3" via env only after the dual-write + backfill
# have run in prod; flipping back is equally a pure env change.
# ---------------------------------------------------------------------------
PAPER_CONTENT_SOURCE = os.environ.get("PAPER_CONTENT_SOURCE", "db").strip().lower()
if PAPER_CONTENT_SOURCE not in {"db", "s3"}:
    PAPER_CONTENT_SOURCE = "db"

# ---------------------------------------------------------------------------
# Logging — stdout/stderr ONLY (statelessness pass P0).
#
# No FileHandler anywhere: an EC2 instance's disk is ephemeral, and the
# process supervisor (gunicorn/systemd) forwards std streams to CloudWatch.
# Without this block, Django's DEFAULT_LOGGING hides django.* console
# output when DEBUG=False and app loggers rely on Python's last-resort
# stderr handler (WARNING+ only) — INFO logs were silently dropped in prod.
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "console": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "console",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
    },
    "loggers": {
        # Request/server errors must surface in prod (DEFAULT_LOGGING gates
        # these behind require_debug_true).
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

