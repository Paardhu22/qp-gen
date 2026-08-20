"""Durable generation runs. See services/generation_runs.py.

The point of these: a generation takes minutes, and before runs were recorded
a dropped connection lost the paper outright. Every test here is about a client
that goes away and comes back.
"""

from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.generation.models import GenerationEvent, GenerationRun
from services.generation_runs import (
    HEARTBEAT_GRACE,
    follow,
    purge_expired_runs,
    reconcile_stale_runs,
    record,
    sse,
    start_run,
)


def _frames(iterator) -> list:
    return list(iterator)


def _no_keepalive(stream, **_kwargs):
    """Pass the stream through unwrapped.

    `keepalive` runs the response iterator on a worker thread so it can emit
    pings while the generator is blocked. That is right in production and
    unusable here: the tests run on an in-memory SQLite database, and reads
    from a second thread hit `database table is locked`. The wrapper has its
    own suite in services/pool/test_keepalive.py; these tests are about what
    the view puts on the wire.
    """
    return stream


class RecordingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            id="ca111111111111111111111111111111",
            name="Teacher",
            email="runs@example.com",
            status="approved",
        )
        self.run = start_run(self.user, kind="questions", request={"topic": "Light"})

    def test_every_frame_is_kept_in_order(self):
        _frames(record(self.run, [sse({"n": 1}), sse({"n": 2}, event="done")]))

        events = list(GenerationEvent.objects.filter(run=self.run).order_by("seq"))
        self.assertEqual([e.seq for e in events], [1, 2])
        self.assertEqual([e.name for e in events], ["message", "done"])

    def test_frames_are_stored_verbatim_so_replay_is_just_bytes(self):
        frame = sse({"question": "What is light?"}, event="question")
        _frames(record(self.run, [frame, sse({}, event="done")]))

        self.assertEqual(
            GenerationEvent.objects.get(run=self.run, seq=1).frame, frame
        )

    def test_pings_are_passed_on_but_not_stored(self):
        # They carry nothing; a later reader gets its own from the keepalive.
        out = _frames(record(self.run, [": ping\n\n", sse({}, event="done")]))

        self.assertIn(": ping\n\n", out)
        self.assertEqual(GenerationEvent.objects.filter(run=self.run).count(), 1)

    def test_a_finished_run_is_marked_completed(self):
        _frames(record(self.run, [sse({}, event="done")]))

        self.run.refresh_from_db()
        self.assertEqual(self.run.status, GenerationRun.STATUS_COMPLETED)
        self.assertIsNotNone(self.run.finished_at)

    def test_a_failing_pipeline_is_recorded_then_re_raised(self):
        def _explode():
            yield sse({"n": 1})
            raise RuntimeError("model is down")

        with self.assertRaises(RuntimeError):
            _frames(record(self.run, _explode()))

        self.run.refresh_from_db()
        self.assertEqual(self.run.status, GenerationRun.STATUS_FAILED)
        self.assertIn("model is down", self.run.error)
        # Whatever arrived before the failure is still there to replay.
        self.assertEqual(GenerationEvent.objects.filter(run=self.run).count(), 1)

    def test_the_stored_request_is_capped_rather_than_unbounded(self):
        # A generation payload can carry a whole pasted syllabus.
        run = start_run(self.user, kind="questions", request={"instructions": "x" * 50_000})
        self.assertLessEqual(len(run.request["instructions"]), 2000)


class FollowingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            id="ca222222222222222222222222222222",
            name="Teacher",
            email="follow@example.com",
            status="approved",
        )
        self.other = User.objects.create(
            id="ca333333333333333333333333333333",
            name="Other",
            email="other-follow@example.com",
            status="approved",
        )
        self.run = start_run(self.user, kind="questions")
        _frames(
            record(
                self.run,
                [
                    sse({"n": 1}, event="question"),
                    sse({"n": 2}, event="question"),
                    sse({"n": 3}, event="done"),
                ],
            )
        )

    def test_a_reader_gets_the_run_id_before_anything_else(self):
        # So a client can re-attach before any real work has happened.
        out = _frames(follow(self.run.id, self.user))
        self.assertIn("event: run", out[0])
        self.assertIn(self.run.id, out[0])

    def test_a_fresh_reader_gets_the_whole_run(self):
        out = _frames(follow(self.run.id, self.user))
        self.assertEqual(len([f for f in out if "event: question" in f]), 2)
        self.assertTrue(any("event: done" in f for f in out))

    def test_a_re_attaching_reader_gets_only_what_it_missed(self):
        out = _frames(follow(self.run.id, self.user, cursor=2))

        self.assertEqual(len([f for f in out if "event: question" in f]), 0)
        self.assertTrue(any("event: done" in f for f in out))

    def test_a_cursor_past_the_end_yields_no_duplicates(self):
        out = _frames(follow(self.run.id, self.user, cursor=99))
        self.assertEqual([f for f in out if "event: question" in f], [])

    def test_another_account_cannot_read_the_run(self):
        # A run id is not a capability.
        out = _frames(follow(self.run.id, self.other))
        self.assertTrue(any("event: error" in f for f in out))
        self.assertFalse(any("event: question" in f for f in out))

    def test_an_unknown_run_ends_with_an_error_rather_than_hanging(self):
        out = _frames(follow("nope", self.user))
        self.assertTrue(any("event: error" in f for f in out))


class AbandonedRunTests(TestCase):
    """A producer whose gunicorn worker was recycled mid-generation."""

    def setUp(self):
        self.user = User.objects.create(
            id="ca444444444444444444444444444444",
            name="Teacher",
            email="stale@example.com",
            status="approved",
        )

    def _stale_run(self):
        run = start_run(self.user, kind="questions")
        GenerationRun.objects.filter(id=run.id).update(
            heartbeat_at=timezone.now() - HEARTBEAT_GRACE - timedelta(minutes=1)
        )
        return GenerationRun.objects.get(id=run.id)

    def test_a_reader_is_told_rather_than_left_waiting(self):
        run = self._stale_run()

        out = _frames(follow(run.id, self.user))

        self.assertTrue(any("event: error" in f for f in out))
        self.assertTrue(any("RunAbandoned" in f for f in out))

    def test_the_run_stops_claiming_to_be_running(self):
        run = self._stale_run()
        _frames(follow(run.id, self.user))

        run.refresh_from_db()
        self.assertEqual(run.status, GenerationRun.STATUS_ABANDONED)

    def test_a_run_still_producing_is_left_alone(self):
        run = start_run(self.user, kind="questions")
        self.assertEqual(reconcile_stale_runs(), 0)
        run.refresh_from_db()
        self.assertEqual(run.status, GenerationRun.STATUS_RUNNING)

    def test_reconciling_settles_every_dead_run_at_once(self):
        self._stale_run()
        self._stale_run()

        self.assertEqual(reconcile_stale_runs(), 2)


class RunRetentionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            id="ca555555555555555555555555555555",
            name="Teacher",
            email="retain@example.com",
            status="approved",
        )

    @override_settings(GENERATION_RUN_RETENTION_DAYS=7)
    def test_an_old_run_and_its_frames_are_purged_together(self):
        run = start_run(self.user, kind="questions")
        _frames(record(run, [sse({}, event="done")]))
        GenerationRun.objects.filter(id=run.id).update(
            created_at=timezone.now() - timedelta(days=8)
        )

        self.assertEqual(purge_expired_runs(), 1)
        self.assertFalse(GenerationRun.objects.filter(id=run.id).exists())
        self.assertFalse(GenerationEvent.objects.filter(run_id=run.id).exists())

    @override_settings(GENERATION_RUN_RETENTION_DAYS=7)
    def test_a_recent_run_survives_the_purge_command(self):
        run = start_run(self.user, kind="questions")
        call_command("purge_generation_runs")
        self.assertTrue(GenerationRun.objects.filter(id=run.id).exists())


class RunEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create(
            id="ca666666666666666666666666666666",
            name="Teacher",
            email="endpoint@example.com",
            status="approved",
        )
        self.other = User.objects.create(
            id="ca777777777777777777777777777777",
            name="Other",
            email="other-endpoint@example.com",
            status="approved",
        )
        self.client.force_authenticate(user=self.user)

    def _finished_run(self, user=None):
        run = start_run(user or self.user, kind="questions", request={"topic": "Light"})
        _frames(record(run, [sse({"n": 1}, event="question"), sse({}, event="done")]))
        return run

    def test_the_list_shows_what_can_be_resumed(self):
        run = self._finished_run()

        response = self.client.get("/api/generation/runs")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["id"], run.id)
        self.assertEqual(response.data[0]["status"], "completed")
        self.assertEqual(response.data[0]["eventCount"], 2)

    def test_the_list_never_shows_another_accounts_runs(self):
        self._finished_run(user=self.other)
        self.assertEqual(self.client.get("/api/generation/runs").data, [])

    def test_re_attaching_replays_from_the_cursor(self):
        run = self._finished_run()

        with patch("apps.generation.views.keepalive", _no_keepalive):
            response = self.client.get(
                f"/api/generation/runs/{run.id}/events?cursor=1"
            )
            body = b"".join(response.streaming_content).decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertIn("event: done", body)
        self.assertNotIn("event: question", body)

    def test_re_attaching_without_a_cursor_replays_everything(self):
        run = self._finished_run()

        with patch("apps.generation.views.keepalive", _no_keepalive):
            body = b"".join(
                self.client.get(
                    f"/api/generation/runs/{run.id}/events"
                ).streaming_content
            ).decode()

        self.assertIn("event: question", body)
        self.assertIn("event: done", body)

    def test_another_accounts_run_is_a_404(self):
        run = self._finished_run(user=self.other)
        response = self.client.get(f"/api/generation/runs/{run.id}/events")
        self.assertEqual(response.status_code, 404)

    def test_a_nonsense_cursor_does_not_error(self):
        run = self._finished_run()
        response = self.client.get(f"/api/generation/runs/{run.id}/events?cursor=abc")
        self.assertEqual(response.status_code, 200)

    def test_starting_a_generation_records_it_and_streams_the_recording(self):
        # `run_in_background` is run inline: the point under test is that the
        # response reads from the RUN, not from the pipeline, so producing it
        # on a thread is exactly the detail that does not matter here.
        def _inline(run, stream_factory):
            _frames(record(run, stream_factory()))

        def _fake_pipeline(**kwargs):
            yield sse({"stage": "pool"}, event="progress")
            yield sse({"paper": "<p>Q1</p>"}, event="done")

        with patch("apps.generation.views.run_in_background", _inline), patch(
            "apps.generation.views.stream_pool_questions", _fake_pipeline
        ), patch("apps.generation.views.keepalive", _no_keepalive):
            response = self.client.post(
                "/api/generation/questions/stream",
                {
                    "topic": "Light",
                    "count": 5,
                    "difficulty": "medium",
                    "instructions": "",
                    "pdfSourceIds": ["abc"],
                },
                format="json",
            )
            body = b"".join(response.streaming_content).decode()

        self.assertEqual(response.status_code, 200)
        # The run id comes first, so the client can re-attach immediately.
        self.assertIn("event: run", body)
        self.assertIn("event: progress", body)
        self.assertIn("event: done", body)

        run = GenerationRun.objects.get(user=self.user)
        self.assertEqual(run.status, GenerationRun.STATUS_COMPLETED)
        # …and the same stream can be replayed afterwards, which is the whole
        # point: the client that dropped mid-generation gets it back.
        with patch("apps.generation.views.keepalive", _no_keepalive):
            replay = b"".join(
                self.client.get(
                    f"/api/generation/runs/{run.id}/events"
                ).streaming_content
            ).decode()
        self.assertIn("event: done", replay)

    def test_a_pending_teacher_cannot_reach_the_runs(self):
        pending = User.objects.create(
            id="ca888888888888888888888888888888",
            name="Pending",
            email="pending-runs@example.com",
            status="pending",
        )
        self.client.force_authenticate(user=pending)
        self.assertEqual(self.client.get("/api/generation/runs").status_code, 403)
