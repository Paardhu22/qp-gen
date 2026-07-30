"use client";

/**
 * Uploading chapters, and waiting for them to be readable.
 *
 * Ingestion is asynchronous: `POST /api/documents/upload` returns a
 * `PdfSource` id long before the chapter is chunked and embedded, so a source
 * is not usable the moment the upload finishes. This hook owns that gap — the
 * "processing" rows, the status poll, and the promotion to ready.
 *
 * It lives on the **page**, not in the Blueprint Builder, and that placement
 * is the point: a teacher who starts a 40 MB upload and closes the modal must
 * come back to a finished upload, not a cancelled one. A modal owns a
 * conversation; it must not own a background job.
 *
 * The readiness gate on the backend is authoritative
 * (`services/source_readiness.py`); this is UX. When the two disagree the
 * server wins, which is what `requeue` is for — see `usePaperGeneration`.
 */

import * as React from "react";

import { fetchForm, fetchJson } from "@/lib/api-client";

export interface UploadedDoc {
  id: string;
  name: string;
  size: number;
}

export interface UploadingDoc {
  tempId: string;
  name: string;
  /** "uploading" = bytes in flight. "processing" = backend is ingesting. */
  status: "uploading" | "processing" | "error";
  error?: string;
  pdfSourceId?: string;
  size?: number;
}

/** How often to ask whether an ingesting source has become readable. */
const POLL_INTERVAL_MS = 3_000;

export function useSourceUploads(
  uploadedDocs: UploadedDoc[],
  setUploadedDocs: React.Dispatch<React.SetStateAction<UploadedDoc[]>>,
) {
  const [uploadingDocs, setUploadingDocs] = React.useState<UploadingDoc[]>([]);

  const uploadFiles = React.useCallback(
    async (files: File[]) => {
      for (const file of files) {
        const tempId = `${Date.now()}-${Math.random()}`;
        const size = file.size;
        setUploadingDocs((prev) => [
          ...prev,
          { tempId, name: file.name, status: "uploading", size },
        ]);

        try {
          const formData = new FormData();
          formData.append("file", file);
          const data = await fetchForm<{
            pdfSourceId: string;
            status?: string;
          }>("/api/documents/upload", formData);

          if (data.status === "ready") {
            // Deduped by SHA-256 — this exact file is already ingested, so
            // there is nothing to wait for.
            setUploadingDocs((prev) => prev.filter((d) => d.tempId !== tempId));
            setUploadedDocs((prev) =>
              prev.some((d) => d.id === data.pdfSourceId)
                ? prev
                : [...prev, { id: data.pdfSourceId, name: file.name, size }],
            );
          } else {
            setUploadingDocs((prev) =>
              prev.map((d) =>
                d.tempId === tempId
                  ? { ...d, status: "processing", pdfSourceId: data.pdfSourceId }
                  : d,
              ),
            );
          }
        } catch (error: any) {
          setUploadingDocs((prev) =>
            prev.map((d) =>
              d.tempId === tempId
                ? { ...d, status: "error", error: error?.message || "Upload failed" }
                : d,
            ),
          );
        }
      }
    },
    [setUploadedDocs],
  );

  // A ref feeds the interval the latest list, so a file added mid-poll is
  // picked up without restarting the timer (which would reset its phase and
  // delay every other in-flight source).
  const uploadingRef = React.useRef<UploadingDoc[]>(uploadingDocs);
  uploadingRef.current = uploadingDocs;

  const hasProcessing = uploadingDocs.some(
    (d) => d.status === "processing" && d.pdfSourceId,
  );

  React.useEffect(() => {
    if (!hasProcessing) return;
    let cancelled = false;

    const poll = async () => {
      const targets = uploadingRef.current.filter(
        (d) => d.status === "processing" && d.pdfSourceId,
      );
      await Promise.all(
        targets.map(async (doc) => {
          try {
            const st = await fetchJson<{ status: string; error?: string | null }>(
              `/api/documents/${doc.pdfSourceId}/status`,
            );
            if (cancelled) return;
            if (st.status === "ready") {
              setUploadingDocs((prev) =>
                prev.filter((d) => d.tempId !== doc.tempId),
              );
              setUploadedDocs((prev) =>
                prev.some((d) => d.id === doc.pdfSourceId)
                  ? prev
                  : [
                      ...prev,
                      {
                        id: doc.pdfSourceId!,
                        name: doc.name,
                        size: doc.size || 0,
                      },
                    ],
              );
            } else if (st.status === "error") {
              setUploadingDocs((prev) =>
                prev.map((d) =>
                  d.tempId === doc.tempId
                    ? { ...d, status: "error", error: st.error || "Processing failed" }
                    : d,
                ),
              );
            }
          } catch {
            // Transient — the next tick retries. A failed poll must not mark
            // a source broken; the source is fine, the network blinked.
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
  }, [hasProcessing, setUploadedDocs]);

  const removeDoc = React.useCallback(
    (id: string) => setUploadedDocs((prev) => prev.filter((d) => d.id !== id)),
    [setUploadedDocs],
  );

  const dismissUpload = React.useCallback(
    (tempId: string) =>
      setUploadingDocs((prev) => prev.filter((d) => d.tempId !== tempId)),
    [],
  );

  /**
   * Reconcile with the backend's readiness gate: forget sources it no longer
   * knows about, and put the merely-unfinished ones back on the poll so the
   * UI recovers on its own instead of stranding the teacher.
   */
  const reconcileNotReady = React.useCallback(
    (pending: { drop: string[]; requeue: { id: string; name: string }[] }) => {
      const stale = new Set([
        ...pending.drop,
        ...pending.requeue.map((p) => p.id),
      ]);
      if (stale.size > 0) {
        setUploadedDocs((prev) => prev.filter((d) => !stale.has(d.id)));
      }
      if (pending.requeue.length > 0) {
        setUploadingDocs((prev) => {
          const known = new Set(prev.map((d) => d.pdfSourceId).filter(Boolean));
          const requeued: UploadingDoc[] = pending.requeue
            .filter((p) => !known.has(p.id))
            .map((p) => ({
              tempId: `requeue-${p.id}`,
              name: p.name,
              status: "processing",
              pdfSourceId: p.id,
            }));
          return requeued.length > 0 ? [...prev, ...requeued] : prev;
        });
      }
    },
    [setUploadedDocs],
  );

  /** True while anything is still uploading or ingesting. */
  const isBusy = uploadingDocs.some(
    (d) => d.status === "uploading" || d.status === "processing",
  );

  return {
    uploadingDocs,
    uploadFiles,
    removeDoc,
    dismissUpload,
    reconcileNotReady,
    isBusy,
  };
}
