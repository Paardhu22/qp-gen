from pathlib import Path
import os
import sys

import dj_database_url
from corsheaders.defaults import default_headers
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env", override=True)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "unsafe-dev-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
if "test" not in sys.argv and not DEBUG and SECRET_KEY == "unsafe-dev-key":
    raise RuntimeError(
        "DJANGO_SECRET_KEY is required when DJANGO_DEBUG=false. "
        "Set it in backend/.env and restart the app."
    )

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
    "apps.chat",
    "apps.documents",
    "apps.generation",
    "apps.organizations",
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


def _bool_env(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on", "t", "y")

STATIC_URL = "static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
AOS_PUBLIC_MEDIA_BASE_URL = os.environ.get("AOS_PUBLIC_MEDIA_BASE_URL", "").rstrip("/")
PDF_IMAGE_MAX_CAPTIONS = _int_env("PDF_IMAGE_MAX_CAPTIONS", 40, minimum=0)
PDF_IMAGE_MIN_BYTES = _int_env("PDF_IMAGE_MIN_BYTES", 8192, minimum=0)
PDF_IMAGE_MIN_DIMENSION = _int_env("PDF_IMAGE_MIN_DIMENSION", 96, minimum=0)

# Store every figure found in an ingested chapter as its own chunk — which
# means one S3 PUT per figure, up to PDF_IMAGE_MAX_CAPTIONS of them, in the
# request path of "apply this source".
#
# Off by default because nothing in the live pipeline reads them any more.
# Model 1 is handed the chapter as Markdown and its rule 7 forbids any
# question that depends on a printed figure; pictures are drawn on demand
# from the editor (services/question_image.py). What remains is the legacy
# retrieval path (services/retrieval_service.retrieve_relevant_chunks with
# require_image=True), so turn this back on if figure-grounded retrieval
# starts mattering again. Chunks ingested while it was on are untouched.
INGEST_EXTRACT_FIGURES = _bool_env("INGEST_EXTRACT_FIGURES", False)

# Chunks per embeddings request. Each batch is one OpenAI round trip inside
# the ingest, so a whole textbook at the old batch size of 50 spent minutes
# in sequential calls. Chunks are ~900-1000 chars (~250 tokens), so 256 of
# them is ~64k tokens — well inside the 300k-token request ceiling for
# text-embedding-3-*, and 5x fewer round trips.
INGEST_EMBED_BATCH_SIZE = _int_env(
    "INGEST_EMBED_BATCH_SIZE", 256, minimum=1, maximum=1024
)

# Compute retrieval embeddings during ingestion at all. Embeddings are read
# only by services/retrieval_service.py (answer-script generation) and the
# flag-gated apps/question_generation/ engine — the pool pipeline that
# actually writes papers reads chunk *text* via services/chapter_markdown.py
# and never touches a vector. Setting this false makes ingestion purely
# local work at the cost of degrading answer-script context for anything
# ingested while it is off.
INGEST_EMBEDDINGS_ENABLED = _bool_env("INGEST_EMBEDDINGS_ENABLED", True)

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

# FRONTEND_URL is the canonical origin — it also builds the links in
# password-reset emails, so it must stay a single value.
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")


def _origins(*values: str) -> list[str]:
    """Normalise and de-duplicate a set of CORS/CSRF origins, order preserved.

    An origin is scheme+host+port with no path and no trailing slash;
    django-cors-headers matches the request's `Origin` header literally, so a
    stray slash silently allows nothing.
    """
    seen: list[str] = []
    for value in values:
        for item in (value or "").split(","):
            origin = item.strip().rstrip("/")
            if origin and origin not in seen:
                seen.append(origin)
    return seen


# Additional browser origins allowed to call the API, comma-separated. Needed
# because CORS matches the Origin header exactly: `https://hsatedu.in` and
# `https://www.hsatedu.in` are different origins, and a deployment reachable at
# both will fail CORS on whichever one FRONTEND_URL does not name. Preview
# deployments and a staging domain belong here too.
#   EXTRA_ALLOWED_ORIGINS=https://www.hsatedu.in,https://staging.hsatedu.in
EXTRA_ALLOWED_ORIGINS = os.environ.get("EXTRA_ALLOWED_ORIGINS", "")

CORS_ALLOWED_ORIGINS = _origins(FRONTEND_URL, EXTRA_ALLOWED_ORIGINS)
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = list(default_headers) + ["X-CSRFToken"]

CSRF_TRUSTED_ORIGINS = _origins(FRONTEND_URL, EXTRA_ALLOWED_ORIGINS)
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
#   POOL_MODEL      — Model 1 (pool generation)
#   REVIEW_MODEL    — Model 2 (paper assembly review)
#   ANSWER_MODEL    — answer-key + answer-script generation
#   CHAT_MODEL      — the dashboard assistant (conversation only, never
#                     generates questions; see services/chat_service.py)
#   OPENAI_EMBEDDING_MODEL — retrieval embeddings (text-embedding-3-small)
#   OPENAI_MODEL    — legacy/blueprint fallback ONLY; nothing above inherits it.
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")

# The dashboard assistant. Deliberately a small, cheap, fast model: it holds a
# conversation and fills in a form, and never writes a question — that is the
# pool pipeline's job, on POOL_MODEL. Independent of OPENAI_MODEL for the same
# reason as every other stage.
CHAT_MODEL = os.environ.get("CHAT_MODEL", "gpt-4.1-mini")

# Per-request ceiling on every OpenAI call. The SDK defaults to 600s, which is
# longer than gunicorn's worker timeout — a hung request would get the worker
# killed mid-stream rather than failing cleanly. Keep this comfortably BELOW
# the gunicorn --timeout in deployment/qp-gen-backend.service.
OPENAI_TIMEOUT_SECONDS = float(os.environ.get("OPENAI_TIMEOUT_SECONDS", "120"))

QG_NEW_ENGINE_ENABLED = os.environ.get("QG_NEW_ENGINE_ENABLED", "false").lower() == "true"

# ENABLE_TEST_ENDPOINTS was removed. It gated exactly one thing —
# /api/generation/test-science-engine — and that is now the management command
# `run_engine_slice`, which cannot be reached over HTTP at all. A flag that
# guards nothing is worse than no flag: it reads as a live safety control, so
# every deployment review spends time confirming a value that has stopped
# meaning anything. If a diagnostic endpoint is ever wanted again, a management
# command is the shape to reach for first.
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

# ─── Independent asset generators (services.assets) ────────────────────────
# Reading passages, grammar tasks and writing prompts are produced by
# generators that never see uploaded content. Only slots whose blueprint names
# one of them are affected — today that is CBSE Class 10 English Sections A
# and B. Everything else routes to the textbook pool as before.
#
#   ASSET_MODEL — model for the asset generators. Falls back to POOL_MODEL.
#     Their prompts carry no chapter, so this can be set independently (and
#     more cheaply) than Model 1.
#   ASSET_REUSE_ENABLED — load previously generated assets from the user's
#     bank as extra candidates. Fresh material is still written every run; this
#     only widens the choice (and is what makes the grammar task pool
#     genuinely reusable). Turn off to make every generation self-contained.
ASSET_MODEL = os.environ.get("ASSET_MODEL", "").strip()
ASSET_REUSE_ENABLED = os.environ.get("ASSET_REUSE_ENABLED", "true").lower() == "true"

# Whole-chapter Markdown handed to Model 1. ~240k chars ≈ 60k tokens, far more
# than any single CBSE chapter; the cap only exists to stop somebody feeding a
# complete textbook through as one "chapter".
CHAPTER_MD_MAX_CHARS = _int_env(
    "CHAPTER_MD_MAX_CHARS", 240_000, minimum=10_000, maximum=2_000_000
)

# ─── How big a pool Model 1 writes ─────────────────────────────────────────
# Exactly what the paper needs, plus only the spares something requires: one
# per OR-choice slot, enough to derive Sets B/C when more than one set is
# asked for, and this margin. See `pipeline._exact_pool_target`.
#
# The margin is not padding. Model 1 output is normalised before it enters the
# pool — malformed objects dropped, duplicates dropped by content hash, a batch
# able to fail all its retries — so asking for exactly N reliably yields
# slightly under N. A paper that is silently three questions short is a worse
# outcome than a few unused questions, and unused ones are banked for reuse
# rather than wasted.
#
# Set to 0 for literally-exact generation, accepting occasional short papers.
POOL_EXACT_MARGIN_PERCENT = _int_env(
    "POOL_EXACT_MARGIN_PERCENT", 15, minimum=0, maximum=100
)

# ─── On-demand question images (services/question_image.py) ────────────────
# Nothing is drawn during generation. A teacher picks a question in the editor,
# chooses a style, and pays for exactly that one image — so there is no
# per-pool cap to configure and no strategy to pick. The speculative image
# stage that used to run between Model 1 and Model 2 (IMAGE_QUESTION_STRATEGY,
# IMAGE_QUESTIONS_PER_POOL, IMAGE_COST_USD_PER_IMAGE) is gone; those settings
# are ignored if still present in a deployment's .env.
#
# Quality is `high` deliberately. A low-tier render draws label text as
# approximate letter shapes, and a student cannot answer "identify the part
# marked B" when B is a smudge — a cheap image on a labelled figure is not a
# cheaper question, it is a broken one. Cost is now bounded by the teacher
# asking, which is the right lever.
OPENAI_IMAGE_MODEL = os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")
OPENAI_IMAGE_SIZE = os.environ.get("OPENAI_IMAGE_SIZE", "1024x1024")
OPENAI_IMAGE_QUALITY = os.environ.get("OPENAI_IMAGE_QUALITY", "high").strip().lower()
# Process-wide ceiling on concurrent image requests. Image generation is slow
# and expensive; a burst from one impatient teacher is the fastest way to hit
# the org's rate limit.
OPENAI_IMAGE_CONCURRENCY = _int_env("OPENAI_IMAGE_CONCURRENCY", 1, minimum=1, maximum=4)

# ---------------------------------------------------------------------------
# Spend reporting — tokens converted to rupees (see services/usage_pricing.py).
#
# A school administrator reads an invoice in rupees, not in tokens, so every
# usage panel reports both. Both knobs exist because both numbers go stale on
# their own schedule: OpenAI reprices models, and the exchange rate moves
# daily. Neither should need a deploy to correct.
#
#   USD_TO_INR              — conversion rate. Default is a working figure;
#                             set it to whatever the finance team reconciles
#                             against.
#   MODEL_PRICING_USD_JSON  — per-model overrides, as
#                             {"model": [prompt_usd_per_mtok, completion_usd_per_mtok]}.
#                             Merged over the built-in table, so a single
#                             corrected model does not require restating all of
#                             them. A malformed value is logged and ignored.
# ---------------------------------------------------------------------------
USD_TO_INR = float(os.environ.get("USD_TO_INR", "88.0") or "88.0")
MODEL_PRICING_USD_JSON = os.environ.get("MODEL_PRICING_USD_JSON", "")

# ---------------------------------------------------------------------------
# Dashboard assistant — how much of a transcript is re-sent each turn.
#
# The assistant re-sends the conversation on every message, so an hour-long
# planning session pays for its own history again at every turn: cost and
# latency grow with the square of the turn count, and a long enough session
# eventually exceeds the context window and starts failing outright. Windowing
# is safe here specifically because the accumulated paper spec lives on the
# Conversation row, not in the transcript — dropping an old turn cannot lose a
# decision the teacher already made.
# ---------------------------------------------------------------------------
CHAT_HISTORY_MAX_MESSAGES = _int_env("CHAT_HISTORY_MAX_MESSAGES", 24, minimum=4, maximum=200)
CHAT_HISTORY_MAX_CHARS = _int_env("CHAT_HISTORY_MAX_CHARS", 24000, minimum=2000, maximum=400000)

# ---------------------------------------------------------------------------
# Recycle bin — how long a deleted paper is recoverable (see apps/projects).
#
# Deleting a paper is one click next to "open", and the thing being deleted is
# a term's worth of a teacher's work. The bin is what makes that click
# survivable.
# ---------------------------------------------------------------------------
PAPER_TRASH_RETENTION_DAYS = _int_env("PAPER_TRASH_RETENTION_DAYS", 30, minimum=1, maximum=365)

# How long an unsaved draft is kept on the server. Must stay in step with
# DRAFT_RETENTION_DAYS in frontend/lib/drafts.ts, which governs the local
# IndexedDB copy — a server copy that outlives the local one would resurrect
# drafts the teacher watched expire, and the reverse would delete work the UI
# said was still there.
DRAFT_RETENTION_DAYS = _int_env("DRAFT_RETENTION_DAYS", 10, minimum=1, maximum=365)

# How long a recorded generation run and its SSE frames are kept, so a client
# that dropped can re-attach. Runs are a delivery mechanism, not a record — the
# questions themselves are already in the bank and the paper in the library —
# so this only needs to outlive "my phone slept during the generation", not
# serve as history. See services/generation_runs.py.
GENERATION_RUN_RETENTION_DAYS = _int_env(
    "GENERATION_RUN_RETENTION_DAYS", 7, minimum=1, maximum=90
)

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
