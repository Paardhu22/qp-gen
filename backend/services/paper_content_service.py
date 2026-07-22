"""Dual-write + flag-gated read for ``PaperSet.content`` (statelessness pass P2).

The DB column ``PaperSet.content`` is the AUTHORITATIVE store in this pass.
Every save additionally mirrors the content to S3 at::

    paper-content/{userId}/{paperId}/{setId}.json

so a later, purely-operational flip of ``PAPER_CONTENT_SOURCE=s3`` can move
reads to S3 with zero code change — and flip back just as cheaply.

Rules this module enforces:

* The S3 mirror is BEST-EFFORT. ``dual_write_set_content`` never raises;
  a failed S3 write must never break a paper save that already committed.
* Only the S3 KEY is persisted (``PaperSet.s3_content_key``) — never a
  presigned URL (see services/media_urls.py for the rationale).
* When reads are flipped to "s3", ANY miss/error falls back to the DB
  column, so a partial backfill or an S3 outage degrades to today's
  behaviour instead of erroring.
* Reuses the existing shared boto3 client in services/s3_client.py — the
  same client/credentials/bucket the export uploads use.
"""

from __future__ import annotations

import logging

from django.conf import settings

from services.s3_client import (  # re-exported for callers/tests: single patch point
    S3NotConfigured,
    download_to_buffer,
    is_configured,
    upload_bytes,
)

logger = logging.getLogger(__name__)

PAPER_CONTENT_PREFIX = "paper-content"


def set_content_s3_key(paper_set) -> str:
    """Deterministic mirror key — one object per set, overwritten in place."""
    return f"{PAPER_CONTENT_PREFIX}/{paper_set.paper.user_id}/{paper_set.paper.id}/{paper_set.id}.json"


def dual_write_set_content(paper_set) -> bool:
    """Mirror ``paper_set.content`` to S3 and record the key on the row.

    Called AFTER the authoritative DB save has committed. Never raises:
    returns True when the mirror (and key bookkeeping) succeeded, False
    otherwise. S3-unconfigured deployments (local dev without a bucket)
    skip silently — the DB column alone is fully sufficient there.
    """
    if not is_configured():
        return False
    try:
        key = set_content_s3_key(paper_set)
        upload_bytes(
            key,
            (paper_set.content or "").encode("utf-8"),
            content_type="application/json",
        )
        if paper_set.s3_content_key != key:
            type(paper_set).objects.filter(pk=paper_set.pk).update(s3_content_key=key)
            paper_set.s3_content_key = key
        return True
    except Exception as exc:
        logger.warning(
            "set-content dual-write to S3 failed for set %s (DB save is "
            "unaffected; backfill command will retry): %s",
            paper_set.id,
            exc,
        )
        return False


def read_set_content(paper_set) -> str:
    """THE single accessor for PaperSet.content reads."""
    source = str(getattr(settings, "PAPER_CONTENT_SOURCE", "db") or "db").lower()
    if source == "s3" and paper_set.s3_content_key and is_configured():
        try:
            return download_to_buffer(paper_set.s3_content_key).decode("utf-8")
        except Exception as exc:
            logger.warning(
                "set-content S3 read failed for set %s (key=%s); "
                "falling back to DB column: %s",
                paper_set.id,
                paper_set.s3_content_key,
                exc,
            )
    return paper_set.content or ""
