/**
 * The one way a paper leaves the editor.
 *
 * There were two: the toolbar's buttons and the editor page's `?action=`
 * URL handler. Same prompt, same container id, same toasts, same S3 backup —
 * written twice. They drifted, and the drift was a defect: the composed-id
 * fix ("{base}_A" is a client-side tab discriminator, not a row the backend
 * knows) was applied to the toolbar copy only, so every URL-param export
 * 404'd its upload while still reporting a successful download. The bug was
 * invisible precisely because the local download is what the teacher sees.
 *
 * One function, so the next fix cannot land in half the places again.
 *
 * The heavy modules are imported at call time rather than at module scope:
 * html2canvas and the docx builder are large, nobody pays for them until an
 * export actually happens, and the editor page already relied on that.
 */

import { toast } from "sonner";

import { persistablePaperId, splitPaperId } from "./paper-id";
import type { ExportType, FileFormat } from "./s3-upload";

const CONTAINER_ID = "tiptap-paper-container";

const LABEL: Record<FileFormat, string> = {
  pdf: "PDF",
  docx: "DOCX",
};

/**
 * Normalise whatever the teacher typed into a filename with exactly one
 * correct extension. Accepts "term test", "term test.pdf" and "term test pdf"
 * and returns the same thing for all three.
 */
function withExtension(raw: string, format: FileFormat): string {
  const trimmed = raw.trim();
  const dotted = new RegExp(`\\.${format}$`, "i");
  if (dotted.test(trimmed)) return trimmed;
  const bare = new RegExp(`\\s*${format}$`, "i");
  return `${trimmed.replace(bare, "").trim()}.${format}`;
}

export interface ExportPaperOptions {
  format: FileFormat;
  exportType: ExportType;
  /**
   * The editor's paper id, composed set suffix and all. Splitting it into the
   * base row plus a set label is this function's job — callers passing the
   * composed id straight through is the bug this file exists to prevent.
   */
  paperId: string | null | undefined;
}

/**
 * Prompt, render, download, and back up in the background.
 *
 * Resolves `false` when the teacher cancels the filename prompt, `true` once
 * the download has been handed to the browser. The cloud backup is
 * deliberately not awaited: it must never delay or fail the local download,
 * which is the part the teacher is waiting for.
 */
export async function exportPaper({
  format,
  exportType,
  paperId,
}: ExportPaperOptions): Promise<boolean> {
  const label = LABEL[format];
  const raw = window.prompt(
    `Enter a filename for the ${label}`,
    `paper-${Date.now()}.${format}`,
  );
  if (!raw || !raw.trim()) return false;

  const filename = withExtension(raw, format);
  const toastId = toast.loading(`Generating ${label}…`);

  try {
    let blob: Blob;
    if (format === "pdf") {
      const { exportToPDF } = await import("./export-pdf");
      blob = await exportToPDF(CONTAINER_ID, filename);
    } else {
      const container = document.getElementById(CONTAINER_ID);
      if (!container) throw new Error("Editor container not found.");
      const { exportToDocx } = await import("./export-docx");
      blob = await exportToDocx(container, filename);
    }

    toast.success(`${label} downloaded!`, { id: toastId });

    // `persistablePaperId` strips the set suffix and returns null for an
    // unsaved draft, so an unsaved paper simply skips the backup rather than
    // posting an id the backend has never seen.
    const backupId = persistablePaperId(paperId);
    if (backupId) {
      const { uploadExportToS3 } = await import("./s3-upload");
      uploadExportToS3(blob, {
        exportType,
        fileFormat: format,
        paperId: backupId,
        setLabel: splitPaperId(paperId).set ?? undefined,
      })
        .then(() => toast.success("Saved to cloud.", { duration: 2000 }))
        .catch((err) => console.error("[S3 upload]", err));
    }

    return true;
  } catch (err) {
    console.error(err);
    toast.error(`Could not export the ${label}. Please try again.`, {
      id: toastId,
    });
    return false;
  }
}
