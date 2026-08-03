"""Durable generation runs: start, reattach, cancel.

`QuestionGenerationStreamView` streams a generation inside the request that
asked for it, which means the run dies with the connection. These endpoints are
the durable path: the run is owned by a worker thread and a row, and the stream
here is a *reader* over the event log rather than the thing producing it. A
client that reloads, loses its network or closes the tab can come back and pick
up exactly where it stopped.

The old view stays. It is still the right shape for anything that genuinely
wants a fire-and-forget stream, and moving every caller at once would be a
bigger change than it is worth.
"""

from __future__ import annotations

import json
import time
from typing import Iterator

from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.generation.models import GenerationRun, GenerationRunEvent
from apps.generation.serializers import QuestionGenerationSerializer
from services.generation_runs import (
    reap_stale_runs,
    request_cancel,
    start_run,
)
from services.pool.pipeline import stream_pool_questions

#: How often the tail checks for new events. Short enough that a question
#: appears promptly, long enough that a dozen idle clients are not a load
#: problem. The pipeline's own pace — a question every few seconds at best —
#: makes anything finer pointless.
POLL_INTERVAL_SECONDS = 0.75

#: Ping cadence while the log is quiet, so a proxy does not close an idle
#: connection mid-generation. Same reasoning as `services/pool/keepalive.py`.
PING_AFTER_IDLE_SECONDS = 15.0


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _run_state(run: GenerationRun) -> dict:
    return {
        "runId": run.id,
        "paperId": run.paper_id,
        "status": run.status,
        "phase": run.phase,
        "produced": run.produced,
        "total": run.total,
        "error": run.error,
    }


class GenerationRunStartView(APIView):
    """POST /api/generation/runs/ — begin a run, return its id immediately."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = QuestionGenerationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated = serializer.validated_data
        payload = request.data

        def stream_factory():
            return stream_pool_questions(
                user=request.user,
                pdf_source_ids=validated.get("pdfSourceIds") or [],
                topic=validated["topic"],
                count=validated["count"],
                difficulty=validated["difficulty"],
                instructions=validated["instructions"],
                payload=payload,
                hsat_source_ids=validated.get("hsatSourceIds") or [],
            )

        run = start_run(
            user=request.user,
            payload=payload,
            paper_id=str(request.data.get("paperId") or ""),
            stream_factory=stream_factory,
        )
        return Response(_run_state(run), status=status.HTTP_201_CREATED)


class GenerationRunStreamView(APIView):
    """GET /api/generation/runs/<id>/stream?afterSeq=N — replay, then tail.

    `afterSeq` is what makes a reattach seamless: the client sends the last
    sequence number it saw and gets everything since, in order, before the tail
    begins. A fresh client sends nothing and replays the run from the start,
    which is how a reload rebuilds a half-written paper.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, run_id: str):
        try:
            run = GenerationRun.objects.get(id=run_id, user=request.user)
        except GenerationRun.DoesNotExist:
            return Response(
                {"error": "No such generation."}, status=status.HTTP_404_NOT_FOUND
            )

        try:
            after_seq = int(request.query_params.get("afterSeq") or 0)
        except (TypeError, ValueError):
            after_seq = 0

        response = StreamingHttpResponse(
            self._tail(run.id, after_seq), content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    def _tail(self, run_id: str, after_seq: int) -> Iterator[str]:
        last_seq = after_seq
        last_emit = time.monotonic()

        while True:
            events = list(
                GenerationRunEvent.objects.filter(
                    run_id=run_id, seq__gt=last_seq
                ).order_by("seq")[:200]
            )

            for record in events:
                # `seq` rides along on every event so the client always knows
                # where to resume from, without tracking it by counting.
                payload = dict(record.payload or {})
                payload["_seq"] = record.seq
                yield _sse(record.event, payload)
                last_seq = record.seq
                last_emit = time.monotonic()

            if events:
                # Drain fast while there is a backlog — a reattaching client
                # should not wait a poll interval per event to catch up.
                continue

            run = GenerationRun.objects.filter(id=run_id).only("status").first()
            if run is None:
                return
            if run.status not in GenerationRun.ACTIVE_STATUSES:
                # Terminal, and the log is drained. The client has everything.
                return

            if time.monotonic() - last_emit > PING_AFTER_IDLE_SECONDS:
                yield ": ping\n\n"
                last_emit = time.monotonic()

            time.sleep(POLL_INTERVAL_SECONDS)


class GenerationRunCancelView(APIView):
    """POST /api/generation/runs/<id>/cancel"""

    permission_classes = [IsAuthenticated]

    def post(self, request, run_id: str):
        try:
            run = GenerationRun.objects.get(id=run_id, user=request.user)
        except GenerationRun.DoesNotExist:
            return Response(
                {"error": "No such generation."}, status=status.HTTP_404_NOT_FOUND
            )

        if run.is_active:
            request_cancel(run)
        return Response(_run_state(run))


class GenerationRunActiveView(APIView):
    """GET /api/generation/runs/active — what is this user running right now?

    The client calls this on load. A run started before a reload is invisible
    to the browser otherwise, and this is what lets the tracker reappear and
    reattach instead of the work looking lost.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Cheap and self-healing: a run whose worker died on the last deploy is
        # reaped the next time anyone asks what is running, so a stale row can
        # never be handed out as live. No cron needed for the common case.
        reap_stale_runs()

        run = (
            GenerationRun.objects.filter(
                user=request.user, status__in=GenerationRun.ACTIVE_STATUSES
            )
            .order_by("-created_at")
            .first()
        )
        if run is None:
            return Response({"run": None})

        last_seq = (
            GenerationRunEvent.objects.filter(run_id=run.id)
            .order_by("-seq")
            .values_list("seq", flat=True)
            .first()
        ) or 0

        state = _run_state(run)
        state["lastSeq"] = last_seq
        return Response({"run": state})
