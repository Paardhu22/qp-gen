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

# AWS Cognito Configuration
AWS_COGNITO_REGION = os.environ.get("AWS_COGNITO_REGION", "ap-south-1")
AWS_COGNITO_USER_POOL_ID = os.environ.get("AWS_COGNITO_USER_POOL_ID", "ap-south-1_zHrjkaeQy")
AWS_COGNITO_APP_CLIENT_ID = os.environ.get("AWS_COGNITO_APP_CLIENT_ID", "3haedrtub40tv44occdolk7ivf")

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
# Vision captioning during PDF ingestion runs against this model instead of the
# main generation model. gpt-4o is used with image detail="low", which OpenAI
# meters at 85 image tokens before text/output tokens; that keeps the
# trignometry.pdf 22-image caption batch inside a typical paid Tier 1 gpt-4o
# budget while still giving useful retrieval captions.
OPENAI_VISION_MODEL = os.environ.get("OPENAI_VISION_MODEL", "gpt-4o")
# Max concurrent vision-API caption requests — enforced PROCESS-WIDE by a
# semaphore in services.openai_service, so parallel chapter ingestion does
# not multiply it. 3 concurrent × ~1,130 tokens per caption call keeps
# in-flight demand around 3,400 tokens against the 30,000 TPM gpt-4o
# ceiling; the previous default of 8 (× 3 parallel chapters = 24 calls)
# saturated TPM and produced 40+ caption failures per book ingest.
PDF_IMAGE_CAPTION_CONCURRENCY = _int_env(
    "PDF_IMAGE_CAPTION_CONCURRENCY", 3, minimum=1, maximum=32
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
if "test" not in sys.argv:
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

