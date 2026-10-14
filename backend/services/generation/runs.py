"""Generation as a durable run, not as the request that happened to start it.

A generation streams SSE for anywhere from thirty seconds to several minutes.
Before this, that stream *was* the run: close the laptop, lose signal, let a
phone sleep, and the paper was gone. The pool questions had been auto-saved to
the bank, but the assembled paper — the thing the teacher was waiting for —
had nowhere to be delivered and no way to be asked for again.

The fix is to separate *producing* the work from *delivering* it:

    pipeline ──▶ record() ──▶ GenerationEvent rows ──▶ follow() ──▶ HTTP
                (one daemon thread)                  (any number of readers,
                                                      arriving whenever)

`record` runs the pipeline once and appends every frame to the run. `follow`
reads frames back out from a cursor and tails the run until it ends. The HTTP
response is only ever a reader, so it can disconnect and a new one can pick up
exactly where it left off.

**What this does not promise.** The producer is a daemon thread inside a
gunicorn worker. A run therefore survives a client disconnect but not a worker
restart — `max-requests` recycling, a deploy, or an OOM kill all end it
mid-flight. `heartbeat_at` is how that stops being invisible: a run whose
producer has stopped writing is marked `abandoned` rather than hanging on as
"running" forever. Surviving a restart needs a real task queue and a broker,
which is a larger change than this one and is deliberately not faked here.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import timedelta
from typing import Callable, Iterable, Iterator, Optional

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone

from apps.generation.models import GenerationEvent, GenerationRun

logger = logging.getLogger("[GENERATION_RUNS]")

#: How often a follower asks the database for new frames.
#:
#: Polling, not a pub/sub channel, because the alternative is a broker this
#: deployment does not have. The interval backs off while nothing is arriving,
#: so a quiet Model-1 batch costs one small indexed query every couple of
#: seconds rather than three a second.
POLL_MIN_SECONDS = 0.25
POLL_MAX_SECONDS = 2.0

#: A producer silent for longer than this is assumed dead — in practice its
#: worker was recycled. Generously above the longest genuine gap between
#: frames, which is a Model 1 batch (a minute or two).
HEARTBEAT_GRACE = timedelta(minutes=5)

#: Frames that end a run, in the wire form the pipeline emits.
_TERMINAL_EVENTS = {"done", "error"}

_EVENT_NAME_RE = re.compile(r"^event:\s*(\S+)", re.MULTILINE)


def retention_days() -> int:
    return int(getattr(settings, "GENERATION_RUN_RETENTION_DAYS", 7))


def _event_name(frame: str) -> str:
    """The SSE event name of a frame, or "" for a comment/ping."""
    match = _EVENT_NAME_RE.search(frame or "")
    return match.group(1) if match else ""


def sse(data: dict, event: str = "message") -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def start_run(user, *, kind: str, request: Optional[dict] = None) -> GenerationRun:
    return GenerationRun.objects.create(
        user=user, kind=kind, request=_safe_request(request or {})
    )


def _safe_request(payload: dict) -> dict:
    """The request, minus anything too large or too sensitive to keep.

    A generation payload can carry an entire pasted syllabus; storing it on
    every run turns a diagnostic aid into a storage problem. Values are capped
    rather than dropped, because a truncated instruction still tells you what
    the run was for.
    """
    out = {}
    for key, value in (payload or {}).items():
        if isinstance(value, str):
            out[key] = value[:2000]
        elif isinstance(value, (int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, (list, tuple)):
            out[key] = [str(v)[:200] for v in value[:50]]
        elif isinstance(value, dict):
            out[key] = {str(k)[:64]: str(v)[:200] for k, v in list(value.items())[:50]}
    return out


def record(run: GenerationRun, stream: Iterable[str]) -> Iterator[str]:
    """Persist every frame of `stream` against `run`, yielding it onward.

    Yields as well as stores so this can be used inline (tests, and any caller
    that wants the old direct-streaming behaviour) rather than only through a
    background thread.
    """
    seq = 0
    terminal = False
    try:
        for frame in stream:
            # Pings carry nothing and would just pad the log; the follower
            # emits its own for whoever is reading later.
            if not frame or frame.startswith(":"):
                yield frame
                continue

            seq += 1
            name = _event_name(frame)
            GenerationEvent.objects.create(run=run, seq=seq, name=name, frame=frame)
            _touch(run, name)
            if name in _TERMINAL_EVENTS:
                terminal = True
            yield frame
    except BaseException as exc:  # noqa: BLE001 — recorded, then re-raised
        _finish(run, GenerationRun.STATUS_FAILED, error=str(exc))
        raise
    else:
        if not terminal:
            # The pipeline ended without saying so. Recorded as completed
            # rather than left running, because a follower would otherwise
            # wait on a producer that has already gone.
            logger.warning("Run %s ended without a terminal event", run.id)
        _finish(run, GenerationRun.STATUS_COMPLETED)


def _touch(run: GenerationRun, name: str) -> None:
    GenerationRun.objects.filter(id=run.id).update(heartbeat_at=timezone.now())


def _finish(run: GenerationRun, status: str, *, error: str = "") -> None:
    GenerationRun.objects.filter(id=run.id).update(
        status=status,
        error=(error or "")[:2000],
        finished_at=timezone.now(),
        heartbeat_at=timezone.now(),
    )


def run_in_background(run: GenerationRun, stream_factory: Callable[[], Iterable[str]]) -> None:
    """Start producing `run` on a daemon thread and return immediately.

    Daemon for the same reason the keepalive pump is: an interpreter shutting
    down must not wait on a thread parked inside an OpenAI call. The thread
    owns its own database connection, so it closes it on the way out — with
    CONN_MAX_AGE set, leaving it open leaks a backend per generation.
    """

    def _produce() -> None:
        try:
            for _ in record(run, stream_factory()):
                pass
        except BaseException:  # noqa: BLE001 — already recorded on the run
            logger.exception("Generation run %s failed", run.id)
        finally:
            close_old_connections()

    threading.Thread(
        target=_produce, name=f"generation-run-{run.id}", daemon=True
    ).start()


def follow(run_id: str, user, *, cursor: int = 0) -> Iterator[str]:
    """Replay a run from `cursor`, then tail it until it ends.

    Scoped to `user`: a run id is not a capability, and one account must not be
    able to read another's paper by guessing one.

    The first frame is always a `run` event carrying the id and the cursor the
    client has reached, so a client that has just started a generation knows
    what to re-attach to, and one that is re-attaching can confirm where it is.
    """
    run = GenerationRun.objects.filter(id=run_id, user=user).first()
    if run is None:
        yield sse({"error": "That generation is no longer available."}, event="error")
        return

    yield sse({"runId": run.id, "kind": run.kind, "cursor": cursor}, event="run")

    interval = POLL_MIN_SECONDS
    while True:
        frames = list(
            GenerationEvent.objects.filter(run_id=run.id, seq__gt=cursor)
            .order_by("seq")
            .values_list("seq", "frame")
        )
        if frames:
            for seq, frame in frames:
                cursor = seq
                yield frame
            interval = POLL_MIN_SECONDS
            continue

        run.refresh_from_db(fields=["status", "heartbeat_at"])
        if run.is_terminal:
            # One last read: a frame could have landed between the query above
            # and the status read, and dropping it would truncate the paper.
            tail = list(
                GenerationEvent.objects.filter(run_id=run.id, seq__gt=cursor)
                .order_by("seq")
                .values_list("seq", "frame")
            )
            for seq, frame in tail:
                cursor = seq
                yield frame
            if run.status == GenerationRun.STATUS_ABANDONED:
                yield _abandoned_frame()
            return

        if _is_stale(run):
            mark_abandoned(run)
            yield _abandoned_frame()
            return

        time.sleep(interval)
        interval = min(interval * 1.5, POLL_MAX_SECONDS)


def _abandoned_frame() -> str:
    return sse(
        {
            "error": (
                "This generation stopped on the server before it finished. "
                "Any questions it produced were saved to your question bank — "
                "start it again to get the paper."
            ),
            "errorType": "RunAbandoned",
            "partial": True,
        },
        event="error",
    )


def _is_stale(run: GenerationRun) -> bool:
    return (
        run.status == GenerationRun.STATUS_RUNNING
        and run.heartbeat_at is not None
        and timezone.now() - run.heartbeat_at > HEARTBEAT_GRACE
    )


def mark_abandoned(run: GenerationRun) -> None:
    logger.warning(
        "Run %s has not produced a frame since %s; marking it abandoned",
        run.id,
        run.heartbeat_at,
    )
    _finish(run, GenerationRun.STATUS_ABANDONED)


def reconcile_stale_runs() -> int:
    """Settle runs whose producer died. Returns how many were marked.

    Called whenever a user lists their runs, so a worker restart does not leave
    a permanent "still generating…" in someone's UI.
    """
    cutoff = timezone.now() - HEARTBEAT_GRACE
    stale = GenerationRun.objects.filter(
        status=GenerationRun.STATUS_RUNNING, heartbeat_at__lt=cutoff
    )
    count = stale.count()
    if count:
        stale.update(
            status=GenerationRun.STATUS_ABANDONED, finished_at=timezone.now()
        )
    return count


def resumable_runs(user):
    """This user's recent runs, newest first, with the stale ones settled."""
    reconcile_stale_runs()
    return GenerationRun.objects.filter(user=user).order_by("-created_at")


def purge_expired_runs(*, now=None) -> int:
    """Drop runs (and their frames) past the retention window.

    Runs are a delivery mechanism, not a record. Once a paper has been received
    the frames are dead weight, and a generation emits a few hundred of them.
    """
    cutoff = (now or timezone.now()) - timedelta(days=retention_days())
    expired = GenerationRun.objects.filter(created_at__lt=cutoff)
    count = expired.count()
    if count:
        expired.delete()
    return count
