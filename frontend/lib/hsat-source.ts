/**
 * The HSAT source domain types.
 *
 * These used to live inside `components/hsat-source-picker.tsx`, and five
 * modules — the readiness poller, the editor page, the blueprint modal, its
 * source panel, and the Tiptap editor — reached into that component to get
 * them. `import type` erases at build time so nothing was being pulled into
 * the bundle, but the direction was still backwards: a leaf dialog owned the
 * vocabulary that the feature is described in, so nothing could talk about an
 * applied source without naming the widget a teacher happens to pick one with.
 *
 * The picker still owns the *response* shapes it decodes (`HsatCatalogResponse`
 * and friends) — those are the wire format of the two endpoints it calls, and
 * nothing else calls them.
 */

/**
 * Where a book or chapter is in the ingest pipeline.
 *
 * `not_ingested` is the resting state, not a failure — every book starts here
 * and stays until the first teacher asks for it. Only `error` is bad.
 */
export type HsatBookStatus =
  | "not_ingested"
  | "pending"
  | "processing"
  | "ready"
  | "error";

/**
 * A book attached to a paper.
 *
 * `status` is a snapshot from the moment it was applied, not a live value —
 * `useHsatReadiness` polls and replaces it. A source is applied by `id` and is
 * usable before it is `ready`, which is why the picker can close immediately
 * and let the book index in the background.
 */
export interface AppliedHsatSource {
  id: string;
  grade: string;
  subject: string;
  book: string;
  status: HsatBookStatus;
  chunkCount: number;
  /** Absent when the whole book was applied rather than a chapter subset. */
  selectedChapterCount?: number;
}
