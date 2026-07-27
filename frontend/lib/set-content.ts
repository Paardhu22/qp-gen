// Which document does an editor set tab (A / B / C) actually show?
//
// Three sources can answer, and getting the precedence wrong is how a teacher
// ends up staring at a blank page — or at the paper they had open before:
//
//   1. `approvedSets`  — a generation the teacher (or the dashboard, on their
//      behalf) approved. Authoritative for EVERY tab, A included, and the only
//      source that carries Set A at all.
//   2. `loadedSets` / `comparisonSets` — sets that exist but were not approved.
//      Consulted for B and C only; see the note on tab A below.
//   3. `paperContent` — the open paper's own content, which IS tab A.
//
// Returning `undefined` means "no content decided here"; the editor then leaves
// the tab to its IndexedDB draft. Returning `""` means "empty document" and is
// NOT the same thing.

import { normalizeSetLabel } from "@/store/editor-store";

export interface TabSet {
  label: string;
  /** Assembled-paper payload (fresh generations). */
  result?: unknown;
  /** Serialised content (saved `PaperSet` rows). */
  content?: string;
}

export interface ResolveTabContentArgs {
  /** The tab being rendered: "A" | "B" | "C". */
  activeSetTab: string;
  /** Approved generations keyed by bare set label. */
  approvedSets: Record<string, unknown> | null | undefined;
  /** Unapproved sets from the latest generation. Persisted across navigation. */
  comparisonSets: TabSet[];
  /** Sets belonging to the currently open saved paper. */
  loadedSets: TabSet[];
  /** The open paper's own content — tab A's authority. */
  paperContent: string | undefined;
}

function serialize(value: unknown): string | undefined {
  if (value === undefined) return undefined;
  return typeof value === "string" ? value : JSON.stringify(value);
}

function findSet(sets: TabSet[], label: string): TabSet | undefined {
  return sets.find((s) => normalizeSetLabel(s.label) === label);
}

export function resolveTabContent({
  activeSetTab,
  approvedSets,
  comparisonSets,
  loadedSets,
  paperContent,
}: ResolveTabContentArgs): string | undefined {
  const approved = approvedSets?.[activeSetTab];
  if (approved !== undefined) return serialize(approved);

  // The `!== "A"` gate is deliberate, not an oversight. `comparisonSets` is
  // persisted, so an unapproved generation outlives the page: without the gate,
  // opening a SAVED paper afterwards would show that stale generation in tab A
  // instead of the paper's own content. Tab A's authority is `paperContent`;
  // B and C have no equivalent, which is the asymmetry this encodes.
  if (activeSetTab !== "A") {
    const sets = comparisonSets.length > 0 ? comparisonSets : loadedSets;
    const match = findSet(sets, activeSetTab);
    if (match) {
      return match.result !== undefined ? serialize(match.result) : match.content;
    }
  }

  return paperContent;
}
