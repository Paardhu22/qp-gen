"""Tests for the SSE keepalive wrapper.

The property that matters in production is negative and invisible: the socket
must never be idle long enough for nginx/gunicorn to cut it, and consumers
must not be able to tell the difference. These tests pin both.
"""

from __future__ import annotations

import json
import threading
import time

from django.test import SimpleTestCase

from services.pool.keepalive import PING, keepalive


class KeepaliveTests(SimpleTestCase):
    def test_passes_frames_through_unchanged_and_in_order(self):
        source = ["event: plan\ndata: {}\n\n", "event: done\ndata: {}\n\n"]
        self.assertEqual(list(keepalive(iter(source), interval=5)), source)

    def test_emits_a_ping_while_the_source_is_slow(self):
        released = threading.Event()

        def _slow():
            yield "event: status\ndata: {}\n\n"
            released.wait(2)
            yield "event: done\ndata: {}\n\n"

        frames = []
        for frame in keepalive(_slow(), interval=0.05):
            frames.append(frame)
            if len(frames) >= 3:
                released.set()

        self.assertEqual(frames[0], "event: status\ndata: {}\n\n")
        self.assertIn(PING, frames)
        self.assertEqual(frames[-1], "event: done\ndata: {}\n\n")

    def test_ping_is_an_sse_comment_so_consumers_ignore_it(self):
        # No `data:` line means every SSE parser — EventSource and the
        # frontend's own splitter — drops the block.
        self.assertTrue(PING.startswith(":"))
        self.assertNotIn("data:", PING)
        self.assertTrue(PING.endswith("\n\n"))

    def test_no_pings_when_the_source_keeps_up(self):
        source = [f"event: question\ndata: {i}\n\n" for i in range(5)]
        out = list(keepalive(iter(source), interval=30))
        self.assertEqual(out, source)

    def test_source_exception_becomes_a_terminal_error_frame(self):
        """The response is already committed when the source fails, so raising
        can only abort the socket. The reason has to travel as an event."""
        def _boom():
            yield "event: plan\ndata: {}\n\n"
            raise RuntimeError("model exploded")

        with self.assertLogs("[SSE_KEEPALIVE]", level="ERROR"):
            frames = list(keepalive(_boom(), interval=5))

        self.assertEqual(frames[0], "event: plan\ndata: {}\n\n")
        self.assertTrue(frames[-1].startswith("event: error\ndata: "))

        payload = json.loads(frames[-1].split("data: ", 1)[1])
        self.assertIn("model exploded", payload["error"])
        self.assertEqual(payload["errorType"], "RuntimeError")
        self.assertTrue(payload["partial"])

    def test_error_after_done_does_not_report_a_failure(self):
        """Bookkeeping that blows up *after* the paper was delivered must not
        turn a successful generation into an error in the UI."""
        def _late_boom():
            yield "event: done\ndata: {}\n\n"
            raise RuntimeError("history write failed")

        with self.assertLogs("[SSE_KEEPALIVE]", level="ERROR"):
            frames = list(keepalive(_late_boom(), interval=5))

        self.assertEqual(frames, ["event: done\ndata: {}\n\n"])

    def test_empty_source_terminates(self):
        self.assertEqual(list(keepalive(iter([]), interval=5)), [])

    def test_early_close_does_not_raise(self):
        """A client disconnect closes the generator mid-stream; that must not
        turn into an error on the way out."""
        def _endless():
            while True:
                yield "event: status\ndata: {}\n\n"
                time.sleep(0.01)

        gen = keepalive(_endless(), interval=5)
        next(gen)
        gen.close()  # raises if the wrapper mishandles GeneratorExit
