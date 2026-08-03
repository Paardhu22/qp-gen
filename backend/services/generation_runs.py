"""Running a generation outside the request that asked for it.

The pipeline used to be consumed directly by `StreamingHttpResponse`, which
tied a multi-minute paper to a single HTTP connection: a reload, a dropped
network or a closed tab destroyed the generator mid-run and the work was gone.
Here the pipeline runs in a worker thread that writes what it emits to
`GenerationRunEvent`, and the stream endpoint becomes a reader over that log.

Threads, not a task queue, because this project has no broker — the only
precedent for background work is `services/hsat_service.py`, which spawns
daemon threads the same way. That is a real constraint and it shapes two things
below: the worker must close its own DB connections (`close_old_connections`),
and it can die without notice on deploy, which is what `reap_stale_runs` is
for.
"""

from __future__ import annotations

import logging
import threading
from datetime import timedelta
from typing import Any, Dict, Iterable, Iterator, Optional

from django.db import close_old_connections, transaction
from django.utils import timezone

from apps.generation.models import GenerationRun, GenerationRunEvent

logger = logging.getLogger(__name__)

#: How long a run may go without a heartbeat before it is presumed dead.
#: Generously above the pipeline's quietest stretch — Model 1 batches emit
#: nothing for minutes — because failing a healthy run is worse than being slow
#: to notice a dead one.
STALE_AFTER = timedelta(minutes=10)

#: How often the worker refreshes `heartbeat_at`, in events. Cheap enough to do
#: often; the point is only to prove the thread still exists.
HEARTBEAT_EVERY_EVENTS = 5


class RunCancelled(Exception):
    """Raised inside the worker when a cancel has been requested."""


def _record_event(run_id: str, seq: int, event: str, payload: Dict[str, Any]) -> None:
    GenerationRunEvent.objects.create(
        run_id=run_id, seq=seq, event=event, payload=payload
    )


def start_run(
    *,
    user,
    payload: Dict[str, Any],
    paper_id: str = "",
    stream_factory,
) -> GenerationRun:
    """Create a run and hand it to a worker thread.

    `stream_factory` is a zero-argument callable returning the SSE generator to
    consume. Injected rather than imported so this module stays independent of
    which pipeline is being run, and so tests can drive it with a list.

    Returns as soon as the row exists — the caller gets an id to stream from,
    not a finished paper.
    """
    run = GenerationRun.objects.create(
        user=user,
        payload=payload,
        paper_id=paper_id or "",
        status=GenerationRun.STATUS_QUEUED,
        phase="Queued",
        heartbeat_at=timezone.now(),
    )

    thread = threading.Thread(
        target=_run_worker,
        args=(run.id, stream_factory),
        name=f"generation-run-{run.id}",
        daemon=True,
    )
    thread.start()
    return run


def _run_worker(run_id: str, stream_factory) -> None:
    """Consume the pipeline, writing every event to the log."""
    seq = 0
    try:
        GenerationRun.objects.filter(id=run_id).update(
            status=GenerationRun.STATUS_RUNNING,
            phase="Starting",
            heartbeat_at=timezone.now(),
        )

        produced = 0
        total = 0
        result: Optional[Dict[str, Any]] = None
        error: Optional[str] = None

        for event, data in _iter_pipeline(stream_factory()):
            # Cancellation is cooperative: the worker is not killed, it notices
            # between events and stops at a coherent point. Checked against the
            # database rather than an in-process flag because the cancel request
            # almost certainly landed on a different gunicorn worker.
            if seq % HEARTBEAT_EVERY_EVENTS == 0 and _cancel_requested(run_id):
                raise RunCancelled()

            seq += 1
            _record_event(run_id, seq, event, data)

            if event == "question":
                produced += 1
                candidate = data.get("total")
                if isinstance(candidate, int) and candidate > 0:
                    total = candidate
            elif event == "plan":
                candidate = data.get("total")
                if isinstance(candidate, int) and candidate > 0:
                    total = candidate
            elif event == "done":
                result = data.get("result") or result
            elif event == "error":
                error = str(data.get("error") or "Generation failed")

            if seq % HEARTBEAT_EVERY_EVENTS == 0:
                GenerationRun.objects.filter(id=run_id).update(
                    produced=produced,
                    total=total,
                    heartbeat_at=timezone.now(),
                )

        GenerationRun.objects.filter(id=run_id).update(
            status=(
                GenerationRun.STATUS_FAILED if error else GenerationRun.STATUS_DONE
            ),
            error=error or "",
            result=result,
            produced=produced,
            total=total,
            phase="Failed" if error else "Paper ready",
            heartbeat_at=timezone.now(),
            finished_at=timezone.now(),
        )

    except RunCancelled:
        GenerationRun.objects.filter(id=run_id).update(
            status=GenerationRun.STATUS_CANCELLED,
            phase="Cancelled",
            heartbeat_at=timezone.now(),
            finished_at=timezone.now(),
        )
        # Recorded as an event too: a client tailing the log needs a terminal
        # event, and polling the row's status is a second thing to get wrong.
        try:
            _record_event(run_id, seq + 1, "cancelled", {})
        except Exception:  # pragma: no cover - best effort
            logger.warning("Could not record cancellation for run %s", run_id)

    except Exception as exc:  # noqa: BLE001 - the thread must never escape
        logger.exception("Generation run %s failed", run_id)
        GenerationRun.objects.filter(id=run_id).update(
            status=GenerationRun.STATUS_FAILED,
            error=str(exc),
            phase="Failed",
            heartbeat_at=timezone.now(),
            finished_at=timezone.now(),
        )
        try:
            _record_event(run_id, seq + 1, "error", {"error": str(exc)})
        except Exception:  # pragma: no cover - best effort
            logger.warning("Could not record failure for run %s", run_id)

    finally:
        # A thread gets its own DB connection and nothing else will hand it
        # back. Same reason `hsat_service` does this at the end of its worker.
        close_old_connections()


def _iter_pipeline(stream: Iterable[Any]) -> Iterator[tuple[str, Dict[str, Any]]]:
    """Normalise the pipeline's output into `(event, data)` pairs.

    The pool pipeline yields pre-rendered SSE text (`event: x\\ndata: {...}`),
    because it was written to be piped straight to a client. Parsing it back is
    the cost of not rewriting the pipeline, and is deliberately tolerant: an
    unparseable chunk is skipped rather than killing a run that is otherwise
    fine.
    """
    import json

    for chunk in stream:
        if not chunk:
            continue
        text = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)

        event = "message"
        data_lines: list[str] = []
        for line in text.split("\n"):
            # Keepalive comments carry nothing and must not become events.
            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())

        if not data_lines:
            continue
        try:
            yield event, json.loads("".join(data_lines))
        except (ValueError, TypeError):
            logger.debug("Skipping unparseable stream chunk on replay path")
            continue


def _cancel_requested(run_id: str) -> bool:
    return GenerationRun.objects.filter(
        id=run_id, cancel_requested=True
    ).exists()


def request_cancel(run: GenerationRun) -> None:
    """Ask a run to stop. The worker notices between events."""
    GenerationRun.objects.filter(id=run.id).update(cancel_requested=True)


def reap_stale_runs(now=None) -> int:
    """Fail runs whose worker has stopped breathing.

    A daemon thread dies with the process, so a deploy or a gunicorn restart
    leaves rows stuck in `running` with no one to finish them. Without this the
    client reattaches to a run that will never emit another event and shows a
    paper being written forever — a spinner that never resolves is a worse
    failure than the crash it is hiding.

    Returns the number of runs failed.
    """
    now = now or timezone.now()
    cutoff = now - STALE_AFTER

    stale = GenerationRun.objects.filter(
        status__in=GenerationRun.ACTIVE_STATUSES,
        heartbeat_at__lt=cutoff,
    )
    count = 0
    for run in stale:
        with transaction.atomic():
            updated = GenerationRun.objects.filter(
                id=run.id, status__in=GenerationRun.ACTIVE_STATUSES
            ).update(
                status=GenerationRun.STATUS_FAILED,
                error=(
                    "This generation stopped unexpectedly, most likely because "
                    "the server restarted while it was running."
                ),
                phase="Interrupted",
                finished_at=now,
            )
            if updated:
                count += 1
                next_seq = (
                    GenerationRunEvent.objects.filter(run_id=run.id).count() + 1
                )
                try:
                    _record_event(
                        run.id,
                        next_seq,
                        "error",
                        {"error": "This generation was interrupted."},
                    )
                except Exception:  # pragma: no cover - best effort
                    logger.warning("Could not record reap event for %s", run.id)
    return count
