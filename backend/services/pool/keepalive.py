"""Keep an SSE generation stream from being killed while it is working.

The generation pipeline goes quiet for minutes at a time. Model 1 emits
nothing until a whole batch of ~20 questions comes back; Model 2's assembly
call and its review pass are single non-streaming requests. Between those the
socket carries no bytes at all.

Nothing in the app notices, but everything between the app and the browser
does. nginx closes a proxied upstream that has been silent for
``proxy_read_timeout`` (60s by default), returning a truncated response; a
load balancer applies its own idle timeout; gunicorn's arbiter kills a sync
worker that has not returned within ``--timeout``. The result is a stream that
simply stops — no ``done`` event, no ``error`` event, nothing the frontend can
report. It only shows up in production, because locally there is no proxy in
front of Django and generations are the only traffic.

``keepalive`` fixes the proxy half of that by guaranteeing the connection is
never idle: the wrapped generator runs on a worker thread while the caller
emits an SSE **comment** line (``: ping``) whenever nothing real has been
produced for ``interval`` seconds. Comments are part of the SSE grammar —
`EventSource` and the frontend's hand-rolled parser both skip any block with
no ``data:`` line — so this is invisible to consumers and needs no contract
change.

It does NOT extend gunicorn's worker timeout; that is a deployment setting
(see deployment/qp-gen-backend.service).
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Iterable, Iterator

from django.db import close_old_connections

logger = logging.getLogger("[SSE_KEEPALIVE]")

#: Seconds of silence before a comment frame is emitted. Comfortably under the
#: 60s nginx default so a misconfigured proxy still survives.
DEFAULT_INTERVAL = 15.0

#: An SSE comment: no `data:` line, so every consumer ignores it.
PING = ": ping\n\n"

_DONE = object()


def keepalive(
    stream: Iterable[str],
    *,
    interval: float = DEFAULT_INTERVAL,
) -> Iterator[str]:
    """Yield everything ``stream`` yields, plus a ping during idle stretches.

    The source runs on a daemon thread. Daemon, because this is consumed by a
    ``StreamingHttpResponse``: a client that disconnects mid-generation causes
    the response iterator to be closed without ever being drained, and a
    non-daemon thread still inside an OpenAI call would then hold up
    interpreter shutdown. It is the same reason the pipeline's own internal
    workers are daemons.

    An exception raised by the source is re-raised here, on the consuming
    thread, so it surfaces exactly as it would have without the wrapper.
    """
    frames: queue.Queue = queue.Queue()
    error: list[BaseException] = []

    def _pump() -> None:
        try:
            for frame in stream:
                frames.put(frame)
        except BaseException as exc:  # noqa: BLE001 - forwarded to the consumer
            error.append(exc)
        finally:
            # The pipeline's DB work (bank auto-save, GenerationHistory) now
            # happens on THIS thread, not the request thread — so Django's
            # request_finished cleanup never sees its connection. With
            # CONN_MAX_AGE set, leaving it open leaks a Postgres backend per
            # generation.
            close_old_connections()
            frames.put(_DONE)

    thread = threading.Thread(target=_pump, name="sse-keepalive", daemon=True)
    thread.start()

    while True:
        try:
            frame = frames.get(timeout=interval)
        except queue.Empty:
            # The pipeline is busy, not stuck. Keep the socket warm.
            yield PING
            continue

        if frame is _DONE:
            break
        yield frame

    # Raised here rather than in a `finally`: a client disconnect closes this
    # generator with GeneratorExit, and re-raising the source's error from a
    # finally block would turn that into a spurious RuntimeError. The pump is
    # a daemon writing to an unbounded queue, so an abandoned run needs no
    # cleanup — it ends with the request.
    if error:
        raise error[0]
