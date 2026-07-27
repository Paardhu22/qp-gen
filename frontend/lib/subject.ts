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
