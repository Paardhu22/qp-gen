"""Tests for the global cap on simultaneous chapter ingests.

Fifteen chapters selected at once used to start fifteen worker threads, each
writing DocumentChunk batches and calling the embeddings API. The cap is what
keeps that from oversubscribing the database write lock and the OpenAI quota
at the same time.
"""

import threading

from django.test import SimpleTestCase

from services import ingest_concurrency
from services.ingest_concurrency import ingest_slot


class IngestSlotTests(SimpleTestCase):
    def test_never_more_than_the_limit_run_at_once(self):
        limit = ingest_concurrency.MAX_CONCURRENT_INGESTS
        overshoot = limit + 6

        lock = threading.Lock()
        live = 0
        peak = 0
        release = threading.Event()

        def _work():
            nonlocal live, peak
            with ingest_slot("test"):
                with lock:
                    live += 1
                    peak = max(peak, live)
                release.wait(5)
                with lock:
                    live -= 1

        threads = [threading.Thread(target=_work) for _ in range(overshoot)]
        for t in threads:
            t.start()

        # Let the first wave settle, sample the peak, then drain.
        threading.Event().wait(0.2)
        with lock:
            observed = peak
        release.set()
        for t in threads:
            t.join(10)

        self.assertLessEqual(observed, limit)
        self.assertEqual(live, 0, "every permit must be returned")

    def test_permit_is_released_when_the_work_raises(self):
        """A crashing ingest must not permanently consume a slot — that would
        starve the queue one failure at a time until nothing ingests at all."""
        for _ in range(ingest_concurrency.MAX_CONCURRENT_INGESTS + 2):
            with self.assertRaises(RuntimeError):
                with ingest_slot("boom"):
                    raise RuntimeError("ingest failed")

        acquired = ingest_concurrency._semaphore.acquire(blocking=False)
        self.assertTrue(acquired, "slots leaked after failed ingests")
        ingest_concurrency._semaphore.release()

    def test_limit_is_clamped_to_something_sane(self):
        self.assertGreaterEqual(ingest_concurrency.MAX_CONCURRENT_INGESTS, 1)
        self.assertLessEqual(ingest_concurrency.MAX_CONCURRENT_INGESTS, 16)
