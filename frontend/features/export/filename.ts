/**
 * Suggested and normalised filenames for exported papers.
 *
 * The old default was `paper-1760000000000.pdf`, which tells a teacher nothing
 * once it sits among forty others in Downloads. The suggestion is built from
 * what the paper already knows about itself.
 */

import type { ExportType, FileFormat } from "./s3-upload";

const ILLEGAL = /[\\/:*?"<>|\u0000-\u001f]/g;

/** Strip characters no major filesystem accepts and tidy the whitespace. */
export function sanitizeFilename(raw: string): string {
  return raw
    .replace(ILLEGAL, " ")
    .replace(/\s+/g, " ")
    .replace(/^[.\s]+|[.\s]+$/g, "")
    .slice(0, 120);
}

/**
 * Accepts "term test", "term test.pdf" and "term test pdf" and returns the
 * same thing for all three: a clean name with exactly one extension.
 */
export function withExtension(raw: string, format: FileFormat): string {
  const trimmed = raw.trim();
  const dotted = new RegExp(`\\.${format}$`, "i");
  if (dotted.test(trimmed)) return trimmed;
  const bare = new RegExp(`\\s*${format}$`, "i");
  return `${trimmed.replace(bare, "").trim()}.${format}`;
}

/** The name without its extension, which is what the dialog lets people edit. */
export function stemOf(name: string): string {
  return name.replace(/\.(pdf|docx)$/i, "");
}

export interface NameParts {
  examName?: string | null;
  className?: string | null;
  subject?: string | null;
  /** "A" | "B" | "C" — only passed when the paper really has several sets. */
  setLabel?: string | null;
  exportType?: ExportType;
}

const TYPE_SUFFIX: Record<ExportType, string> = {
  question_paper: "",
  answer_script: "Answer Key",
  question_bank: "Question Bank",
};

/**
 * "Mid-Term Exam - Class 10 Science - Set A", without the extension.
 * Falls back to "Question Paper" so the result is never empty.
 */
export function suggestExportName({
  examName,
  className,
  subject,
  setLabel,
  exportType = "question_paper",
}: NameParts): string {
  const cls = (className ?? "").trim();
  const classPart = cls
    ? /^class\b/i.test(cls)
      ? cls
      : `Class ${cls}`
    : "";
  const classAndSubject = [classPart, (subject ?? "").trim()]
    .filter(Boolean)
    .join(" ");

  const exam = (examName ?? "").trim();
  // "Science Unit Test" + "Class 10 Science" should not say Science twice.
  const subjectAlreadyNamed =
    exam && subject && exam.toLowerCase().includes(subject.trim().toLowerCase());

  const parts = [
    exam,
    subjectAlreadyNamed ? classPart : classAndSubject,
    setLabel ? `Set ${setLabel.replace(/^set\s*/i, "")}` : "",
    TYPE_SUFFIX[exportType],
  ].filter(Boolean);

  const name = sanitizeFilename(parts.join(" - "));
  return name || "Question Paper";
}
