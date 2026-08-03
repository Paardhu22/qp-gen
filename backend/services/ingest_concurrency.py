"""One global cap on how many chapter ingests run at the same time.

Both ingest entry points — an uploaded PDF (`document_service._spawn_pdf_worker`)
and a library book (`hsat_service.ingest_hsat_book_async`) — answer their
request immediately and hand the heavy work to a daemon thread. That is the
right shape: an ingest outlives the dialog that started it. What was missing is
a ceiling. Selecting fifteen chapters started fifteen threads, and each one
extracts, captions, embeds and writes concurrently, which oversubscribes three
separate resources at once:

* **the database** — every worker writes ``DocumentChunk`` batches. On SQLite
  that is a single write lock (see ``apps/common/db_pragmas``); on Postgres it
  is a connection per worker on top of the request pool.
* **the OpenAI embeddings quota** — fifteen parallel batch requests is a fast
  route to a 429, and a retry storm on top of it.
* **memory** — each worker holds its whole decoded PDF buffer.

The fix is not to make ingestion serial; it is to make it *bounded*. Threads
past the limit block on the semaphore and start as earlier ones finish, so the
queue drains at a rate the box can actually sustain. Nothing user-visible
changes: those chapters were already showing a "processing" row and were
already going to take a while.

The permit is acquired **inside** the worker thread, never on the request
thread — blocking the request would undo the whole point of ingesting in the
background.
"""

from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager

logger = logging.getLogger(__name__)


def _limit_from_env() -> int:
    """Read the cap, clamped to something sane.

    Defaults to 4: enough that a handful of chapters still overlap and the
    wall-clock win of concurrency survives, low enough that the embeddings
    quota and the SQLite write lock are not the bottleneck.
    """
    raw = os.environ.get("INGEST_MAX_CONCURRENCY", "4")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid INGEST_MAX_CONCURRENCY=%r; using 4", raw)
        return 4
    return max(1, min(value, 16))


MAX_CONCURRENT_INGESTS = _limit_from_env()

_semaphore = threading.BoundedSemaphore(MAX_CONCURRENT_INGESTS)


@contextmanager
def ingest_slot(label: str = ""):
    """Hold one of the ingest permits for the duration of the block.

    Call this from the worker thread, wrapping the heavy work — not from the
    request handler.
    """
    waited = not _semaphore.acquire(blocking=False)
    if waited:
        logger.info(
            "Ingest %s queued — %d concurrent ingests already running",
            label or "job",
            MAX_CONCURRENT_INGESTS,
        )
        _semaphore.acquire()
    try:
        yield
    finally:
        _semaphore.release()
