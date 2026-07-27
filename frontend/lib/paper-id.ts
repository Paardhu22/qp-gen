/**
 * Paper ids and the A/B/C set suffix.
 *
 * The editor renders one TipTap instance per set tab and identifies each with
 * a composed id `"{baseId}_{A|B|C}"`. Only the BASE id is a real backend row —
 * the suffix is a purely client-side tab discriminator used to key the
 * per-tab IndexedDB draft.
 *
 * Keeping the two forms straight matters because they used to be built and
 * torn apart with inline string math in three different files, which let a
 * composed id leak back into a place expecting a base id and pick up a second
 * suffix ("current_A" -> "current_A_A" -> "current_A_A_A"). Autosave then
 * PUT /papers/current_A_A and the editor logged "Paper not found" forever.
 *
 * Backend paper ids are cuids (lowercase alphanumeric, no underscore), so
 * stripping a trailing `_A|_B|_C` can never damage a genuine id.
 */

export type SetLabel = "A" | "B" | "C";

const SET_SUFFIX = /_([ABC])$/;

/** The local-draft sentinel used when no backend paper row exists yet. */
export const DRAFT_PAPER_ID = "current";

/**
 * Split a possibly-composed id into its base and set label.
 *
 * Strips *repeated* suffixes so ids already corrupted by the old inline
 * concatenation heal on load. The set label reported is the outermost one
 * (the tab the id was last composed for).
 */
export function splitPaperId(id: string | null | undefined): {
  base: string | null;
  set: SetLabel | null;
} {
  if (!id) return { base: null, set: null };
  let base = id;
  let set: SetLabel | null = null;
  let match = base.match(SET_SUFFIX);
  while (match) {
    if (!set) set = match[1] as SetLabel;
    base = base.slice(0, -2);
    match = base.match(SET_SUFFIX);
  }
  return { base: base || null, set };
}

/** The backend row id, with any set suffix removed. */
export function basePaperId(id: string | null | undefined): string | null {
  return splitPaperId(id).base;
}

/** Compose the per-tab editor id for a set. */
export function withSetSuffix(
  id: string | null | undefined,
  set: string,
): string {
  const base = basePaperId(id) || DRAFT_PAPER_ID;
  return `${base}_${set}`;
}

/**
 * True when the id refers to a local-only draft rather than a saved row.
 * Accepts composed or base ids.
 */
export function isDraftPaperId(id: string | null | undefined): boolean {
  const base = basePaperId(id);
  return !base || base === DRAFT_PAPER_ID;
}

/**
 * The id that belongs in the `?paperId=` URL param and in a live document's
 * `paperId` field: a real backend id, or null for an unsaved draft.
 */
export function persistablePaperId(id: string | null | undefined): string | null {
  const base = basePaperId(id);
  return !base || base === DRAFT_PAPER_ID ? null : base;
}
