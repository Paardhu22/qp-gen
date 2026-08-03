"""Make SQLite survive the concurrency this app actually generates.

Production is Postgres, but local development runs on SQLite
(``DATABASE_URL=sqlite:///db.sqlite3``) and the ingest path is genuinely
concurrent: every upload spawns a worker thread that writes ``DocumentChunk``
rows in batches, and a generation writes the question bank from the SSE
keepalive thread at the same time.

SQLite's default rollback-journal mode gives the whole database a single
writer *and* blocks readers for the duration of every write, so a handful of
parallel ingests serialise into a pile-up and the losers raise
``OperationalError: database is locked``. Three pragmas remove most of that:

* ``journal_mode=WAL`` — readers no longer block on a writer, which is the
  single biggest win. WAL is persistent (stored in the database header), so
  this only has to succeed once, but re-issuing it is free.
* ``busy_timeout`` — a connection that finds the write lock held waits for it
  instead of failing instantly. Django's ``OPTIONS["timeout"]`` only covers
  connections it opens itself; the pragma applies to every connection,
  including the worker threads'.
* ``synchronous=NORMAL`` — safe under WAL (a crash can lose the last commits
  but cannot corrupt the file) and much faster for the bulk_create batches.

Everything here is a no-op on Postgres, so it is safe to leave registered.
"""

from __future__ import annotations

import logging

from django.db.backends.signals import connection_created

logger = logging.getLogger(__name__)

#: How long a blocked writer waits for the lock before giving up. An embedding
#: batch commit is milliseconds; 30s is far beyond any legitimate wait and only
#: matters when something is badly wrong.
BUSY_TIMEOUT_MS = 30_000

_registered = False


def apply_sqlite_pragmas(sender=None, connection=None, **kwargs) -> None:
    """Tune a freshly opened SQLite connection for concurrent writers."""
    if connection is None or connection.vendor != "sqlite":
        return

    # `:memory:` databases (the test suite) have no shared file to contend
    # over, and WAL is not supported there — skip rather than log a failure.
    if connection.settings_dict.get("NAME") in (":memory:", "", None):
        return

    try:
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS};")
    except Exception:
        # A database we cannot tune still works, just less well under load.
        # Never let this stop a connection from being usable.
        logger.warning("Could not apply SQLite pragmas", exc_info=True)


def register() -> None:
    """Connect the hook once. Idempotent — ``ready()`` can run twice."""
    global _registered
    if _registered:
        return
    connection_created.connect(apply_sqlite_pragmas, dispatch_uid="sqlite_pragmas")
    _registered = True
