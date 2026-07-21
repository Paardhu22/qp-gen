"""Authoritative source-readiness validation for generation.

The async upload flow (``document_service.process_pdf_upload(background=True)``)
returns a ``PdfSource`` id immediately, while extraction / captioning / embedding
run on a worker thread. Before the async change the upload was synchronous, so an
id the client held was, by construction, fully ingested — the pipeline never had
to check. Now readiness must be enforced *server-side*, because the pipeline
builds its chapter purely from persisted ``DocumentChunk`` rows
(``services.chapter_markdown.build_chapter_markdown``): a source that is still
``processing`` (0 or partial chunks) yields an empty/thin chapter and the generic
"No questions could be generated from this chapter" dead-end.

This module is the single, authoritative gate. It:
  * scopes every ``pdfSourceId`` to the requesting user (ownership),
  * rejects any source not in ``ready`` state,
  * verifies the source actually has persisted chunks,
and returns a structured list of the offending sources so the caller can emit a
``DOCUMENTS_NOT_READY`` SSE event instead of the generic error.

The frontend polling / button-disabling stays as a UX nicety; THIS is the source
of truth.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from apps.documents.models import DocumentChunk, HsatSource, PdfSource

#: SSE `code` for the terminal readiness failure (matches the frontend handler).
DOCUMENTS_NOT_READY = "DOCUMENTS_NOT_READY"

# Per-document reasons, most-specific first.
REASON_NOT_FOUND = "not_found"   # unknown id, deleted, or owned by another user
REASON_NOT_READY = "not_ready"   # exists + owned, but status != "ready"
REASON_NO_CHUNKS = "no_chunks"   # status "ready" but no persisted chunks


@dataclass(frozen=True)
class PendingSource:
    """One source that is not usable for generation yet."""

    id: str
    name: Optional[str]
    kind: str          # "pdf" | "hsat"
    status: str        # backend status at check time ("processing", "ready", …)
    reason: str        # one of the REASON_* constants above

    def to_wire(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "status": self.status,
            "reason": self.reason,
        }


def _ids_with_chunks(*, pdf_ids: Sequence[str], hsat_ids: Sequence[str]) -> set:
    """Return the subset of ids (pdf or hsat) that have ≥1 persisted chunk.

    One DISTINCT query per source kind — cheap, and the authoritative check for
    "the document contains persisted chunks".
    """
    have: set = set()
    if pdf_ids:
        have |= {
            str(x)
            for x in DocumentChunk.objects.filter(pdf_source_id__in=pdf_ids)
            .values_list("pdf_source_id", flat=True)
            .distinct()
        }
    if hsat_ids:
        have |= {
            str(x)
            for x in DocumentChunk.objects.filter(hsat_source_id__in=hsat_ids)
            .values_list("hsat_source_id", flat=True)
            .distinct()
        }
    return have


def check_sources_ready(
    *,
    user,
    pdf_source_ids: Optional[Sequence[str]] = None,
    hsat_source_ids: Optional[Sequence[str]] = None,
) -> List[PendingSource]:
    """Validate every requested source. Empty result = safe to generate.

    PDF sources are scoped to ``user`` (ownership); HSAT books are shared global
    content, so they are validated for readiness only. Both kinds must be in
    ``ready`` state AND have persisted chunks.
    """
    pdf_ids = [str(x) for x in (pdf_source_ids or []) if x]
    hsat_ids = [str(x) for x in (hsat_source_ids or []) if x]
    pending: List[PendingSource] = []

    # ── PDF sources — ownership-scoped ──────────────────────────────────────
    owned: Dict[str, PdfSource] = {}
    if pdf_ids:
        owned = {
            str(s.id): s
            for s in PdfSource.objects.filter(id__in=pdf_ids, user=user)
        }

    # ── HSAT sources — shared, readiness only ───────────────────────────────
    hsat_map: Dict[str, HsatSource] = {}
    if hsat_ids:
        hsat_map = {
            str(s.id): s for s in HsatSource.objects.filter(id__in=hsat_ids)
        }

    # Which "ready" sources actually have chunks (single pass, both kinds).
    ready_pdf_ids = [sid for sid, s in owned.items() if s.status == "ready"]
    ready_hsat_ids = [sid for sid, s in hsat_map.items() if s.status == "ready"]
    with_chunks = _ids_with_chunks(pdf_ids=ready_pdf_ids, hsat_ids=ready_hsat_ids)

    for sid in pdf_ids:
        src = owned.get(sid)
        if src is None:
            # Unknown id, deleted, or another user's source — do not leak which.
            pending.append(
                PendingSource(id=sid, name=None, kind="pdf",
                              status="unknown", reason=REASON_NOT_FOUND)
            )
        elif src.status != "ready":
            pending.append(
                PendingSource(id=sid, name=src.name, kind="pdf",
                              status=src.status, reason=REASON_NOT_READY)
            )
        elif sid not in with_chunks:
            pending.append(
                PendingSource(id=sid, name=src.name, kind="pdf",
                              status=src.status, reason=REASON_NO_CHUNKS)
            )

    for sid in hsat_ids:
        src = hsat_map.get(sid)
        if src is None:
            pending.append(
                PendingSource(id=sid, name=None, kind="hsat",
                              status="unknown", reason=REASON_NOT_FOUND)
            )
        elif src.status != "ready":
            pending.append(
                PendingSource(id=sid, name=src.book, kind="hsat",
                              status=src.status, reason=REASON_NOT_READY)
            )
        elif sid not in with_chunks:
            pending.append(
                PendingSource(id=sid, name=src.book, kind="hsat",
                              status=src.status, reason=REASON_NO_CHUNKS)
            )

    return pending


def build_not_ready_payload(pending: Sequence[PendingSource]) -> Dict[str, object]:
    """Build the ``DOCUMENTS_NOT_READY`` SSE payload for a list of pending sources."""
    named = [p.name for p in pending if p.name]
    missing = [p for p in pending if p.reason == REASON_NOT_FOUND]

    if named:
        subjects = ", ".join(named)
        if all(p.reason == REASON_NOT_READY for p in pending if p.name):
            message = (
                f"{subjects} is still being processed. Wait for it to finish, "
                "then generate again."
            )
        else:
            message = (
                f"These sources aren't ready yet: {subjects}. Wait for processing "
                "to finish, then generate again."
            )
    elif missing:
        message = (
            "One or more selected sources could not be found. Remove them and "
            "re-add your documents, then generate again."
        )
    else:
        message = (
            "Your sources are still being processed. Wait for them to finish, "
            "then generate again."
        )

    return {
        "code": DOCUMENTS_NOT_READY,
        "error": message,
        "pendingDocuments": [p.to_wire() for p in pending],
    }
