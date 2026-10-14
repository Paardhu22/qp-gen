/** Uploaded PDF sources: upload, readiness, subject detection, analysis and validation. */
"use client";

import { ApiError, fetchForm, fetchJson } from "@/lib/api/http";

/**
 * Ingest a PDF and return the source the chat can reference.
 *
 * Tries the presigned direct-to-S3 route first and falls back to a server
 * upload, mirroring components/file-upload.tsx. That duplication is
 * deliberate for now: the upload component interleaves progress reporting
 * with each step, and unpicking it is a bigger change than this needs.
 */
export async function uploadPdfSource(file: File): Promise<UploadedSource> {
  let presign: {
    url?: string;
    fields?: Record<string, string>;
    key?: string;
  } | null = null;

  try {
    presign = await fetchJson<{
      url?: string;
      fields?: Record<string, string>;
      key?: string;
    }>("/api/documents/presign", {
      method: "POST",
      body: JSON.stringify({
        name: file.name,
        content_type: file.type,
        size: file.size,
      }),
    });
  } catch {
    presign = null;
  }

  if (presign?.url && presign.fields && presign.key) {
    try {
      const s3form = new FormData();
      Object.entries(presign.fields).forEach(([k, v]) => s3form.append(k, v));
      s3form.append("file", file);

      const uploadRes = await fetch(presign.url, {
        method: "POST",
        body: s3form,
      });
      if (!uploadRes.ok) {
        throw new Error(`S3 rejected the upload (${uploadRes.status})`);
      }

      return await fetchJson<UploadedSource>("/api/documents/confirm", {
        method: "POST",
        body: JSON.stringify({
          key: presign.key,
          name: file.name,
          content_type: file.type,
        }),
      });
    } catch (error) {
      // Fall through to the server upload rather than failing the attachment.
      // A presigned POST straight from the browser is the one step in this
      // flow that depends on the bucket's CORS rules, and those are set
      // outside the app — when they are wrong (or the bucket is in another
      // region, or an extension blocks the cross-origin POST) every direct
      // upload fails while the server-side route is perfectly healthy. That
      // is exactly the state the generator form has always been in, since it
      // only ever used the server route.
      console.warn("Direct-to-S3 upload failed, falling back to server:", error);
    }
  }

  const formData = new FormData();
  formData.append("file", file);
  return fetchForm<UploadedSource>("/api/documents/upload", formData);
}

export interface UploadedSource {
  pdfSourceId: string;
  /** "ready" for a deduped/cached source, otherwise "processing". */
  status?: string;
  warnings?: string[];
}

export interface SourceStatus {
  id: string;
  status: string;
  chunk_count: number;
  error?: string | null;
}

export async function fetchSourceStatus(
  sourceId: string,
): Promise<SourceStatus> {
  return fetchJson<SourceStatus>(`/api/documents/${sourceId}/status`, {
    method: "GET",
  });
}

/**
 * Block until an uploaded PDF is actually usable.
 *
 * Ingestion runs on a worker thread and the upload returns as soon as the row
 * is saved, so a source is normally `processing` for a while after it appears
 * to have uploaded. The generation endpoint refuses a request that names one
 * (`DOCUMENTS_NOT_READY`), so attaching without waiting produces a Generate
 * button that fails minutes later for no visible reason.
 */
export async function waitForPdfSource(
  sourceId: string,
  { timeoutMs = 240000, intervalMs = 2000 }: { timeoutMs?: number; intervalMs?: number } = {},
): Promise<SourceStatus> {
  const deadline = Date.now() + timeoutMs;

  for (;;) {
    const status = await fetchSourceStatus(sourceId);
    if (status.status === "ready") return status;
    if (status.status === "error") {
      throw new ApiError(
        status.error || "This PDF could not be processed.",
        422,
      );
    }
    if (Date.now() > deadline) {
      throw new ApiError(
        "This PDF is taking unusually long to process. It will keep going — " +
          "try again in a minute.",
        504,
      );
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

export interface DetectSubjectResponse {
  detected: boolean;
  subject: string | null;
  confidence: number;
  error?: string | null;
}

export async function detectPdfSubject(file: File): Promise<DetectSubjectResponse> {
  const formData = new FormData();
  formData.append("file", file);
  return fetchForm<DetectSubjectResponse>("/api/documents/detect-subject", formData);
}

export interface PdfAnalysisResult {
  fileName: string;
  hash: string;
  subject: string | null;
  board: string | null;
  class: string | null;
  chapter: string | null;
  documentType: string;
  confidence: number;
  isEducational: boolean;
  pagesAnalyzed: number;
  error?: string | null;
  fromCache?: boolean;
}

export interface PdfValidationMismatch {
  file?: string;
  subject?: string;
  board?: string;
  class?: string;
  chapter?: string;
  documentType?: string;
  reason?: string;
}

export interface PdfValidationReport {
  valid: boolean;
  errorType?: "SUBJECT_MISMATCH" | "BOARD_MISMATCH" | "CLASS_MISMATCH" | "UNSUPPORTED_DOCUMENT" | "LOW_CONFIDENCE";
  message?: string;
  mismatches: PdfValidationMismatch[];
  subject?: string | null;
  board?: string | null;
  class?: string | null;
  chapter?: string | null;
  chapters?: string[];
}

export async function analyzePdfDocument(file: File): Promise<PdfAnalysisResult> {
  const formData = new FormData();
  formData.append("file", file);
  return fetchForm<PdfAnalysisResult>("/api/documents/analyze-pdf", formData);
}

export async function validatePdfMetadata(documents: PdfAnalysisResult[]): Promise<PdfValidationReport> {
  return fetchJson<PdfValidationReport>("/api/documents/validate-metadata", {
    method: "POST",
    body: JSON.stringify({ documents }),
  });
}



// ── General Instructions Mode: designing a paper from prose ─────────────
//
// `/design-paper` reads free-form instructions and returns the paper they
// describe plus the constraints they did not settle. Cheap (one small model
// call), writes nothing, and safe to call while the teacher is still typing —
// callers debounce it. See `services/paper_design.py`.
