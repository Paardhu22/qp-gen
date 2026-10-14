// Flattening the generation stream's `plan` event into a status line.
//
// The event's `summary` field is an OBJECT, not a sentence. The backend builds
// it in `services/generation_router.py::summarize_question_plan` —
// `total_questions`, `total_marks`, `or_choices`, `image_questions`,
// `exact_counts`, `section_marks`, `section_questions` —
// and the general-instructions branch of `services/pool/pipeline.py` emits a
// smaller two-key form of the same shape. Handing either straight to React as
// a text child throws "Objects are not valid as a React child" and takes the
// whole page down mid generation, which loses the stream with it.

/** A short human line describing the compiled blueprint. Always a string. */
export function planSummaryLine(summary: unknown): string {
  if (typeof summary === "string") return summary;
  if (!summary || typeof summary !== "object") return "";
  const s = summary as Record<string, unknown>;

  const parts: string[] = [];
  if (typeof s.total_questions === "number") {
    parts.push(`${s.total_questions} question${s.total_questions === 1 ? "" : "s"}`);
  }
  if (typeof s.total_marks === "number") parts.push(`${s.total_marks} marks`);

  const sections = s.section_questions;
  if (sections && typeof sections === "object" && !Array.isArray(sections)) {
    const count = Object.keys(sections).length;
    if (count > 0) parts.push(`${count} section${count === 1 ? "" : "s"}`);
  }

  return parts.length ? `Blueprint compiled — ${parts.join(" · ")}` : "";
}

/** Anything the stream hands us for a status line, made safe to render. */
export function asStatusText(value: unknown): string {
  return typeof value === "string" ? value : "";
}
