"""Server-side drafts: the copy of unsaved work that survives the device.

The editor's local IndexedDB store is still the authority for speed — every
keystroke goes there, and nothing here is on that path. This is the second
copy, pushed on a debounce, so a draft started on a laptop can be finished on
the staffroom PC and a cleared cache is an inconvenience rather than a loss.

Two rules run through all of it:

*   **Last write wins, on the client's clock.** Two devices editing the same
    draft have to be ordered by when the teacher typed, not by which push
    reached the server first — a slow connection would otherwise let a stale
    device overwrite newer work simply by being slower.
*   **A draft is unsaved work, and only unsaved work.** Saving as a paper
    deletes the draft: it has a real Paper row now, that row is authoritative,
    and a leftover draft would be a second copy quietly diverging from it.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.projects.models import Draft

logger = logging.getLogger("[DRAFT_SERVICE]")

#: Hard ceiling on one draft document, in bytes of serialized JSON.
#:
#: A paper with several dozen questions and inline figure markup runs to a few
#: hundred kilobytes; this is generous room above that. It exists because the
#: body is client-supplied and otherwise unbounded, and a request that would
#: put a multi-megabyte blob in a row on every debounce tick is a denial of
#: service dressed up as an autosave.
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024

#: Valid set labels, plus "" for the legacy un-suffixed document.
VALID_SET_LABELS = {"", "A", "B", "C"}


class DraftRejected(ValueError):
    """The draft cannot be stored, with a reason fit to show a teacher."""


def retention_days() -> int:
    return int(getattr(settings, "DRAFT_RETENTION_DAYS", 10))


def _cutoff():
    return timezone.now() - timedelta(days=retention_days())


def normalize_scope(scope: str) -> str:
    cleaned = (scope or "").strip()
    if not cleaned:
        raise DraftRejected("That draft has no id, so there is nowhere to store it.")
    if len(cleaned) > 64:
        raise DraftRejected("That draft id is not one we recognise.")
    return cleaned


def normalize_set_label(label) -> str:
    cleaned = (label or "").strip().upper()
    if cleaned not in VALID_SET_LABELS:
        raise DraftRejected(f"'{label}' is not a set this paper can have.")
    return cleaned


def upsert_draft(
    user,
    *,
    scope: str,
    set_label: str,
    document: dict,
    client_updated_at: int,
) -> tuple[Draft, bool]:
    """Store one draft. Returns `(draft, stored)`.

    `stored` is False when the incoming copy is older than what is already on
    the server — the caller gets the newer row back so it can reconcile rather
    than silently keep typing into a stale document.
    """
    scope = normalize_scope(scope)
    set_label = normalize_set_label(set_label)

    if not isinstance(document, dict):
        raise DraftRejected("That draft is not in a shape we can store.")
    size = len(json.dumps(document, ensure_ascii=False).encode("utf-8"))
    if size > MAX_DOCUMENT_BYTES:
        raise DraftRejected(
            "This paper is too large to keep a server copy of. It is still saved "
            "in this browser — save it as a paper to keep it safely."
        )

    try:
        client_updated_at = int(client_updated_at or 0)
    except (TypeError, ValueError):
        client_updated_at = 0

    metadata = document.get("metadata") or {}
    existing = Draft.objects.filter(user=user, scope=scope, set_label=set_label).first()

    if existing and existing.client_updated_at > client_updated_at:
        # Another device has newer work. Refusing here is the whole point of
        # tracking the client clock — accepting would lose it.
        return existing, False

    fields = {
        "title": str(document.get("title") or metadata.get("title") or "")[:255],
        "class_name": str(metadata.get("className") or "")[:100],
        "subject": str(metadata.get("subject") or "")[:255],
        "document": document,
        "client_updated_at": client_updated_at,
    }

    if existing:
        for key, value in fields.items():
            setattr(existing, key, value)
        existing.save(update_fields=[*fields.keys(), "updated_at"])
        return existing, True

    return (
        Draft.objects.create(user=user, scope=scope, set_label=set_label, **fields),
        True,
    )


def list_drafts(user):
    """Every live draft for this user, newest first, without the bodies.

    `.defer("document")` matters here for the same reason the papers list
    defers set content: the strip renders titles and dates, and loading a
    dozen whole TipTap documents to draw them is the difference between a
    fast page and a slow one.
    """
    purge_expired_drafts()
    return (
        Draft.objects.filter(user=user, updated_at__gte=_cutoff())
        .defer("document")
        .order_by("-client_updated_at")
    )


def get_scope(user, scope: str):
    """Every set tab of one draft, for hydrating the editor."""
    return Draft.objects.filter(user=user, scope=normalize_scope(scope)).order_by(
        "set_label"
    )


def delete_scope(user, scope: str) -> int:
    """Drop a whole draft — every set tab of it. Returns rows removed.

    Called both when a teacher deletes a draft and when one is saved as a
    paper: from that moment the Paper row is authoritative, and a surviving
    draft would be a second copy diverging from it.
    """
    deleted, _ = Draft.objects.filter(user=user, scope=normalize_scope(scope)).delete()
    return deleted


def purge_expired_drafts(*, now=None) -> int:
    """Remove drafts untouched for longer than the retention window."""
    cutoff = (now or timezone.now()) - timedelta(days=retention_days())
    expired = Draft.objects.filter(updated_at__lt=cutoff)
    count = expired.count()
    if count:
        expired.delete()
    return count
