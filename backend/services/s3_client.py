"""Shared boto3 client for HSAT and other server-side S3 access.

`default_storage` (django-storages S3Boto3Storage) is great for *user
uploads* — every key it touches gets prefixed and routed through the
file-storage abstraction. The HSAT bucket holds shared, server-side
content whose keys are known up front, so we use boto3 directly.

Credentials come from Django settings (which read them from env). No
secrets are ever hard-coded; if the env is missing we raise.
"""

from __future__ import annotations

import logging
import threading
import time
from io import BytesIO
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

logger = logging.getLogger("[S3_CLIENT]")

_client_lock = threading.Lock()
_client_cache: dict = {}


class S3NotConfigured(RuntimeError):
    """Raised when AWS credentials / bucket are missing from settings."""


def _hsat_bucket() -> str:
    # HSAT source textbooks have their own bucket/region (settings.HSAT_S3_*),
    # which may differ from the uploads bucket. Fall back to the uploads bucket
    # for single-bucket deployments.
    return getattr(settings, "HSAT_S3_BUCKET", "") or getattr(
        settings, "AWS_STORAGE_BUCKET_NAME", ""
    )


def _hsat_region() -> Optional[str]:
    return (
        getattr(settings, "HSAT_S3_REGION", "")
        or getattr(settings, "AWS_S3_REGION_NAME", None)
        or None
    )


def is_configured() -> bool:
    return bool(_hsat_bucket())


def get_client():
    """Return a thread-safe cached boto3 S3 client.

    boto3 clients are NOT thread-safe across regions but reusing one is
    fine here because we always target a single bucket from settings.
    """
    if not is_configured():
        raise S3NotConfigured(
            "AWS_STORAGE_BUCKET_NAME is missing from the environment."
        )
    with _client_lock:
        client = _client_cache.get("client")
        if client is not None:
            return client
        endpoint = getattr(settings, "AWS_S3_ENDPOINT_URL", None) or None
        config = BotoConfig(
            retries={"max_attempts": 5, "mode": "standard"},
            signature_version=getattr(settings, "AWS_S3_SIGNATURE_VERSION", "s3v4"),
            s3={"addressing_style": getattr(settings, "AWS_S3_ADDRESSING_STYLE", "auto")},
            # Fail fast on a stalled S3 read instead of letting the worker
            # thread hang for the default (60 s × retries) ≈ minutes per
            # chapter. With our outer 3-attempt retry these settle into a
            # bounded ~3×60 s ceiling per download.
            connect_timeout=10,
            read_timeout=60,
        )
        client = boto3.client(
            "s3",
            # Sign for the HSAT bucket's OWN region — not the uploads region —
            # or cross-region GetObject fails with 403 AuthorizationHeaderMalformed.
            region_name=_hsat_region(),
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
            endpoint_url=endpoint,
            config=config,
        )
        _client_cache["client"] = client
        return client


def get_bucket() -> str:
    bucket = _hsat_bucket()
    if not bucket:
        raise S3NotConfigured(
            "HSAT_S3_BUCKET (or AWS_STORAGE_BUCKET_NAME) is not set."
        )
    return bucket


def head_object(key: str) -> dict:
    """Cheap probe — raises ClientError(404) if the object is missing."""
    return get_client().head_object(Bucket=get_bucket(), Key=key)


def download_to_buffer(
    key: str, *, max_attempts: int = 3, backoff_base: float = 0.5
) -> bytes:
    """Download an S3 object into memory with bounded retries.

    Retries only on transient errors (network / 5xx); permission and
    not-found errors are raised immediately so the caller can surface a
    useful message instead of stalling.
    """
    last_exc: Optional[BaseException] = None
    for attempt in range(1, max_attempts + 1):
        buf = BytesIO()
        try:
            get_client().download_fileobj(get_bucket(), key, buf)
            data = buf.getvalue()
            if not data:
                raise RuntimeError(f"Empty download for key={key!r}")
            return data
        except ClientError as exc:
            code = (exc.response.get("Error") or {}).get("Code") or ""
            status = (
                exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") or 0
            )
            # Don't retry on 404 / 403 — they won't get better.
            if code in {"NoSuchKey", "404", "AccessDenied", "403"} or status in (
                403,
                404,
            ):
                raise
            last_exc = exc
        except (BotoCoreError, OSError) as exc:
            last_exc = exc
        if attempt < max_attempts:
            sleep_for = backoff_base * (2 ** (attempt - 1))
            logger.warning(
                "S3 download retry %s/%s for %s after %s (sleep %.2fs)",
                attempt,
                max_attempts,
                key,
                last_exc,
                sleep_for,
            )
            time.sleep(sleep_for)
    assert last_exc is not None
    raise last_exc
