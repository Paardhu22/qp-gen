/**
 * Subject identification for layout decisions.
 *
 * The generator form sends the literal "English", but a paper's stored subject
 * can be any of the aliases the backend normalises (see `_SUBJECT_ALIASES` in
 * `services/generation_router.py`): "English Language and Literature",
 * "English Core", "english language". An exact `=== "english"` match silently
 * drops the English layout for every one of those, so match on the prefix.
 */
export function isEnglishSubject(subject: unknown): boolean {
  return String(subject ?? "")
    .trim()
    .toLowerCase()
    .startsWith("english");
}

/** The classes the Builder offers. */
export const PAPER_CLASSES = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"];

/** The subjects the Builder offers, in the order its pickers show them. */
export const PAPER_SUBJECTS = [
  "Science",
  "Social Science",
  "Mathematics",
  "English",
  "Hindi",
  "Telugu",
  "Sanskrit",
  "Computer Science",
  "ICT",
];

/**
 * The `PAPER_SUBJECTS` entry a stored subject belongs to.
 *
 * A board template carries its display name — "English Language & Literature",
 * "Hindi Course B" — which matches no entry exactly. The backend already
 * normalises these aliases; this only decides which picker entry lights up.
 */
export function paperSubjectEntry(subject: unknown): string | undefined {
  const lower = String(subject ?? "").trim().toLowerCase();
  if (!lower) return undefined;
  return (
    PAPER_SUBJECTS.find((s) => s.toLowerCase() === lower) ??
    PAPER_SUBJECTS.find((s) => lower.startsWith(s.toLowerCase()))
  );
}
