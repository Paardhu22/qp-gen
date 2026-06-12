"""Dual-write + flag-gated read for ``Paper.content`` (statelessness pass P2).

The DB column ``Paper.content`` is the AUTHORITATIVE store in this pass.
Every save additionally mirrors the content to S3 at::

    paper-content/{userId}/{paperId}.json

so a later, purely-operational flip of ``PAPER_CONTENT_SOURCE=s3`` can move
reads to S3 with zero code change — and flip back just as cheaply.

Rules this module enforces:

* The S3 mirror is BEST-EFFORT. ``dual_write_paper_content`` never raises;
  a failed S3 write must never break a paper save that already committed.
* Only the S3 KEY is persisted (``Paper.s3_content_key``) — never a
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


def paper_content_s3_key(paper) -> str:
    """Deterministic mirror key — one object per paper, overwritten in place."""
    return f"{PAPER_CONTENT_PREFIX}/{paper.user_id}/{paper.id}.json"


def dual_write_paper_content(paper) -> bool:
    """Mirror ``paper.content`` to S3 and record the key on the row.

    Called AFTER the authoritative DB save has committed. Never raises:
    returns True when the mirror (and key bookkeeping) succeeded, False
    otherwise. S3-unconfigured deployments (local dev without a bucket)
    skip silently — the DB column alone is fully sufficient there.
    """
    if not is_configured():
        return False
    try:
        key = paper_content_s3_key(paper)
        upload_bytes(
            key,
            (paper.content or "").encode("utf-8"),
            content_type="application/json",
        )
        if paper.s3_content_key != key:
            # queryset.update() so a pure bookkeeping write never bumps the
            # auto_now `updated_at` (same pattern as answer_script_id).
            type(paper).objects.filter(pk=paper.pk).update(s3_content_key=key)
            paper.s3_content_key = key
        return True
    except Exception as exc:
        logger.warning(
            "paper-content dual-write to S3 failed for paper %s (DB save is "
            "unaffected; backfill command will retry): %s",
            paper.id,
            exc,
        )
        return False


def read_paper_content(paper) -> str:
    """THE single accessor for Paper.content reads.

    PAPER_CONTENT_SOURCE == "db" (default): return the DB column unchanged —
    identical to pre-pass behaviour, S3 is never touched.

    PAPER_CONTENT_SOURCE == "s3": try the mirrored object first; ANY miss or
    error (no key yet, S3 down, empty object) falls back to the DB column.
    """
    source = str(getattr(settings, "PAPER_CONTENT_SOURCE", "db") or "db").lower()
    if source == "s3" and paper.s3_content_key and is_configured():
        try:
            return download_to_buffer(paper.s3_content_key).decode("utf-8")
        except Exception as exc:
            logger.warning(
                "paper-content S3 read failed for paper %s (key=%s); "
                "falling back to DB column: %s",
                paper.id,
                paper.s3_content_key,
                exc,
            )
    return paper.content or ""
