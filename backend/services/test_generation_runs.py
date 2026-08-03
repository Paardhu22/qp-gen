"""Tests for durable generation runs.

Concentrated on the two things that fail *silently* if they are wrong: the
reaper (without it a dead run shows as a paper being written forever) and the
event-log parsing (a run whose events never land looks like a generation that
produced nothing).
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.generation.models import GenerationRun, GenerationRunEvent
from services.generation_runs import (
    STALE_AFTER,
    _iter_pipeline,
    reap_stale_runs,
    request_cancel,
)


class IterPipelineTests(TestCase):
    """The pipeline yields rendered SSE text; the worker has to read it back."""

    def test_parses_event_and_data(self):
        chunks = [
            'event: question\ndata: {"section": "A", "index": 3}\n\n',
            'event: done\ndata: {"result": {"sections": []}}\n\n',
        ]
        parsed = list(_iter_pipeline(chunks))
        self.assertEqual(
            parsed,
            [
                ("question", {"section": "A", "index": 3}),
                ("done", {"result": {"sections": []}}),
            ],
        )

    def test_skips_keepalive_comments(self):
        """A ping carries no data and must not become an event."""
        parsed = list(_iter_pipeline([": ping\n\n"]))
        self.assertEqual(parsed, [])

    def test_skips_unparseable_chunk_without_killing_the_run(self):
        """One bad chunk must not lose the events that follow it."""
        chunks = [
            "event: status\ndata: {not json}\n\n",
            'event: status\ndata: {"message": "fine"}\n\n',
        ]
        parsed = list(_iter_pipeline(chunks))
        self.assertEqual(parsed, [("status", {"message": "fine"})])

    def test_defaults_event_name_when_absent(self):
        parsed = list(_iter_pipeline(['data: {"a": 1}\n\n']))
        self.assertEqual(parsed, [("message", {"a": 1})])


class ReapStaleRunsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(email="reaper@example.com")

    def _run(self, *, status, heartbeat_age):
        return GenerationRun.objects.create(
            user=self.user,
            status=status,
            heartbeat_at=timezone.now() - heartbeat_age,
        )

    def test_fails_a_run_whose_worker_stopped_breathing(self):
        """A deploy kills the daemon thread; nothing else moves the row."""
        run = self._run(
            status=GenerationRun.STATUS_RUNNING,
            heartbeat_age=STALE_AFTER + timedelta(minutes=1),
        )

        self.assertEqual(reap_stale_runs(), 1)

        run.refresh_from_db()
        self.assertEqual(run.status, GenerationRun.STATUS_FAILED)
        self.assertIn("stopped unexpectedly", run.error)
        self.assertIsNotNone(run.finished_at)

    def test_emits_a_terminal_event_so_a_tailing_client_stops(self):
        run = self._run(
            status=GenerationRun.STATUS_RUNNING,
            heartbeat_age=STALE_AFTER + timedelta(minutes=1),
        )
        reap_stale_runs()

        events = GenerationRunEvent.objects.filter(run_id=run.id)
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.first().event, "error")

    def test_leaves_a_healthy_run_alone(self):
        """Failing a live generation is worse than noticing a dead one late."""
        run = self._run(
            status=GenerationRun.STATUS_RUNNING,
            heartbeat_age=timedelta(seconds=5),
        )

        self.assertEqual(reap_stale_runs(), 0)

        run.refresh_from_db()
        self.assertEqual(run.status, GenerationRun.STATUS_RUNNING)

    def test_leaves_a_finished_run_alone(self):
        """An old `done` row is not stale, it is finished."""
        run = self._run(
            status=GenerationRun.STATUS_DONE,
            heartbeat_age=STALE_AFTER + timedelta(hours=2),
        )

        self.assertEqual(reap_stale_runs(), 0)

        run.refresh_from_db()
        self.assertEqual(run.status, GenerationRun.STATUS_DONE)

    def test_reaping_twice_does_not_double_report(self):
        """The second sweep must not re-fail what it already failed."""
        self._run(
            status=GenerationRun.STATUS_RUNNING,
            heartbeat_age=STALE_AFTER + timedelta(minutes=1),
        )
        self.assertEqual(reap_stale_runs(), 1)
        self.assertEqual(reap_stale_runs(), 0)


class CancelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(email="canceller@example.com")

    def test_request_cancel_sets_the_flag_the_worker_watches(self):
        run = GenerationRun.objects.create(
            user=self.user, status=GenerationRun.STATUS_RUNNING
        )
        self.assertFalse(run.cancel_requested)

        request_cancel(run)

        run.refresh_from_db()
        self.assertTrue(run.cancel_requested)
