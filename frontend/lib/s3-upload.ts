/**
 * Upload a generated export (PDF/DOCX) to S3 via the backend.
 *
 * This is a fire-and-forget helper: callers should not await it in the
 * critical path. The local browser download always happens first; this
 * function backs it up to cloud storage in the background.
 *
 * On failure it throws — callers are expected to `.catch()` and log.
 */

import { API_BASE_URL } from "./api-base-url";
import { getAccessToken } from "./token-storage";

export type ExportType = "question_paper" | "answer_script" | "question_bank";
export type FileFormat = "pdf" | "docx";

export interface UploadExportOptions {
  exportType: ExportType;
  fileFormat: FileFormat;
  /**
   * Base paper ID — required for question_paper and answer_script, omit for
   * question_bank. Must NOT carry the editor's `_A`/`_B`/`_C` set suffix;
   * that is a client-side tab discriminator and no such row exists.
   */
  paperId?: string | null;
  /**
   * Which set this export is of ("A" | "B" | "C"). The backend records the
   * key on that set, so exporting Set B no longer overwrites Set A's object.
   * Defaults server-side to the paper's first set.
   */
  setLabel?: string;
}

const CONTENT_TYPE: Record<FileFormat, string> = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
};

export async function uploadExportToS3(
  blob: Blob,
  options: UploadExportOptions,
): Promise<{ s3_key: string }> {
  const { exportType, fileFormat, paperId, setLabel } = options;

  const formData = new FormData();
  // Re-type the blob so the server sees the correct Content-Type in the multipart body.
  const typedBlob = new Blob([blob], { type: CONTENT_TYPE[fileFormat] });
  formData.append("file", typedBlob, `export.${fileFormat}`);
  formData.append("export_type", exportType);
  formData.append("file_format", fileFormat);
  if (paperId) formData.append("paper_id", paperId);
  if (setLabel) formData.append("set_label", setLabel);

  const headers: Record<string, string> = {};
  const token = getAccessToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(`${API_BASE_URL}/api/storage/upload-export/`, {
    method: "POST",
    headers,
    body: formData,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      (body as Record<string, string>)?.error ?? `S3 upload failed (${response.status})`,
    );
  }

  return response.json() as Promise<{ s3_key: string }>;
}
