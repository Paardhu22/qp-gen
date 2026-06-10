"""Single authority for media-object URL resolution.

The storage model is: the DATABASE only ever holds the permanent storage
path (S3 object key or MEDIA_ROOT-relative path). Presigned URLs are
minted at the moment of use and never persisted — a presigned URL stored
at ingest time is guaranteed stale by the time a teacher generates a
paper hours or days later (the `invalid_image_url` OpenAI 400).

Two URL flavours, two audiences:

* ``stable_media_url(path)`` — an app-stable ``/media/<path>`` URL that
  never expires. Safe to persist in chunk metadata, question payloads,
  and TipTap documents. Served by ``apps.common.views.serve_media``,
  which redirects to a fresh signed URL when storage is remote.

* ``fresh_signed_media_url(path)`` — a short-lived signed URL minted at
  call time. ONLY for immediate consumption (OpenAI vision download,
  the /media/ redirect response). Never store it.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings
from django.core.files.storage import default_storage

logger = logging.getLogger("[MEDIA_URLS]")

#: Expiry for signed URLs that are consumed immediately after minting.
#: 15 minutes comfortably covers an OpenAI vision fetch (or a browser
#: redirect follow) without leaving long-lived signed URLs in the wild.
FRESH_URL_EXPIRE_SECONDS = 900


def is_remote_storage() -> bool:
    """True when default_storage writes to S3/MinIO instead of MEDIA_ROOT."""
    return bool(getattr(settings, "AWS_STORAGE_BUCKET_NAME", ""))


def stable_media_url(storage_path: str) -> str:
    """Permanent app URL for a stored object — never signed, never expires.

    ``AOS_PUBLIC_MEDIA_BASE_URL`` (CDN / split-origin deployments) is
    prepended when configured, mirroring the previous behaviour of
    ``_public_media_url`` minus the presigning.
    """
    if not storage_path:
        return ""
    media_url = getattr(settings, "MEDIA_URL", "/media/") or "/media/"
    if not media_url.endswith("/"):
        media_url += "/"
    relative = f"{media_url}{storage_path.lstrip('/')}"
    public_base = getattr(settings, "AOS_PUBLIC_MEDIA_BASE_URL", "")
    return f"{public_base}{relative}" if public_base else relative


def fresh_signed_media_url(
    storage_path: str, expire: int = FRESH_URL_EXPIRE_SECONDS
) -> str:
    """Mint a fresh URL for *immediate* use (OpenAI fetch / redirect).

    With S3Boto3Storage this is a presigned GET valid for ``expire``
    seconds. FileSystemStorage doesn't accept ``expire`` and returns the
    plain ``/media/...`` URL — callers that need a model-readable URL
    must check the scheme and fall back (e.g. to a base64 data URL).
    """
    if not storage_path:
        return ""
    try:
        return default_storage.url(storage_path, expire=expire)
    except TypeError:
        # Storage backend without expiry support (local filesystem).
        return default_storage.url(storage_path)
    except Exception as exc:
        logger.warning("Could not sign URL for %s: %s", storage_path, exc)
        return ""


def normalise_chunk_payload(payload: dict) -> dict:
    """Rewrite a retrieved chunk payload so image_url is the stable URL.

    Chunks ingested before the stable-URL fix persisted a presigned URL in
    ``metadata.image_url`` (X-Amz-Expires=3600 — long expired). Whenever a
    chunk also carries ``image_storage_path`` we rebuild image_url from the
    permanent path, so every downstream consumer (prompt text, allowed-URL
    validation, the question payload the frontend renders) sees a URL that
    cannot go stale. Mutates and returns ``payload``.
    """
    metadata = payload.get("metadata") or {}
    storage_path = metadata.get("image_storage_path")
    if storage_path:
        stable = stable_media_url(str(storage_path))
        if stable:
            metadata["image_url"] = stable
            payload["image_url"] = stable
    return payload


def vision_url_for_chunk(metadata: dict) -> Optional[str]:
    """Freshly-signed, model-downloadable URL for a chunk's source image.

    Returns None when no remote signed URL can be minted (local storage,
    missing path) — the caller falls back to inlining base64 bytes.
    """
    storage_path = metadata.get("image_storage_path")
    if not storage_path or not is_remote_storage():
        return None
    url = fresh_signed_media_url(str(storage_path))
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return None
