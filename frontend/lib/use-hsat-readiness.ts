"use client";

/**
 * Watching an applied library book become readable.
 *
 * The HSAT picker used to hold its dialog open, spinner and all, until the
 * whole book finished indexing — minutes, on first use, of a modal that could
 * do nothing else. It now applies the book and closes, which moves the wait
 * out of the teacher's way but leaves the source sitting at "Preparing this
 * book…" with nothing to advance it. This hook is that something.
 *
 * It is the HSAT twin of the poll inside `useSourceUploads`, and it lives on
 * the **page** for the same reason: an ingest that outlives the modal must be
 * observed by something that also outlives the modal.
 *
 * As with uploads, this is UX. `services/source_readiness.py` is the
 * authoritative gate — a book that is not really ready fails generation with
 * `DOCUMENTS_NOT_READY` regardless of what this hook believes.
 */

import * as React from "react";

import { fetchJson } from "@/lib/api-client";
import type { AppliedHsatSource } from "@/lib/hsat-source";

/** Ingestion runs in minutes, so a slow poll is plenty. */
const POLL_INTERVAL_MS = 5_000;

interface HsatStatusResponse {
  status: AppliedHsatSource["status"];
  chunk_count: number;
  error?: string | null;
}

export function useHsatReadiness(
  hsatSources: AppliedHsatSource[],
  setHsatSources: React.Dispatch<React.SetStateAction<AppliedHsatSource[]>>,
) {
  // The interval reads the live list through a ref so a book applied mid-poll
  // is picked up without restarting the timer — restarting would reset its
  // phase and delay every other book still indexing.
  const sourcesRef = React.useRef<AppliedHsatSource[]>(hsatSources);
  sourcesRef.current = hsatSources;

  const pending = hsatSources.some(
    (s) => s.status === "pending" || s.status === "processing",
  );

  React.useEffect(() => {
    if (!pending) return;
    let cancelled = false;

    const poll = async () => {
      const targets = sourcesRef.current.filter(
        (s) => s.status === "pending" || s.status === "processing",
      );
      await Promise.all(
        targets.map(async (source) => {
          try {
            const st = await fetchJson<HsatStatusResponse>(
              `/api/hsat/sources/${source.id}/status/`,
            );
            if (cancelled || st.status === source.status) return;
            setHsatSources((prev) =>
              prev.map((s) =>
                s.id === source.id
                  ? { ...s, status: st.status, chunkCount: st.chunk_count }
                  : s,
              ),
            );
          } catch {
            // Transient — the next tick retries. A failed poll must not mark
            // a book broken; the book is fine, the network blinked.
          }
        }),
      );
    };

    void poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [pending, setHsatSources]);
}
