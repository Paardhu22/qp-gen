"""Tests for the SSE keepalive wrapper.

The property that matters in production is negative and invisible: the socket
must never be idle long enough for nginx/gunicorn to cut it, and consumers
must not be able to tell the difference. These tests pin both.
"""

from __future__ import annotations

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

    def test_source_exception_reaches_the_consumer(self):
        def _boom():
            yield "event: plan\ndata: {}\n\n"
            raise RuntimeError("model exploded")

        gen = keepalive(_boom(), interval=5)
        self.assertEqual(next(gen), "event: plan\ndata: {}\n\n")
        with self.assertRaisesMessage(RuntimeError, "model exploded"):
            list(gen)

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
