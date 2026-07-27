/**
 * The arithmetic behind page-fit decisions, separated from the DOM.
 *
 * Pagination is a feedback loop: every transaction changes the layout the next
 * pass measures. That makes it prone to a specific class of bug — the rule that
 * pulls a block UP disagreeing with the rule that pushes a block DOWN, so the
 * two fight each other forever, burn the pass ceiling, and freeze the document
 * half-paginated with pages left short. The disagreement is pure arithmetic,
 * which means it can be tested without a browser; that is what this module is
 * for (see scripts/test-pagination-fit.mjs).
 *
 * The one invariant that matters:
 *
 *     canPullUp(m) === true   ⟹   overflowAfterPull(m) <= 0
 *
 * i.e. a block the engine agrees to pull up can never overflow the page it
 * lands on, so the split rule can never send it straight back.
 */

/**
 * Breathing room, in px, kept below the last block on a page.
 *
 * Small on purpose, and it can afford to be: both inputs below are measured
 * from the live layout rather than estimated, so this guards against sub-pixel
 * rounding rather than covering an unknown.
 */
export const FIT_TOLERANCE = 4;

export type FitMeasurements = {
  /** Unused px below the last block, measured to the content-box bottom. */
  free: number;
  /** Px the incoming block's collapsed top margin will add at the join. */
  joinGap: number;
  /** Px spanned by the run being moved, margins between its blocks included. */
  runHeight: number;
};

/** Whether the run fits in what is left of the page. */
export function canPullUp({ free, joinGap, runHeight }: FitMeasurements): boolean {
  return joinGap + runHeight + FIT_TOLERANCE <= free;
}

/**
 * How far past the content-box bottom the page would end up, in px, if the run
 * were moved. Zero or less means it fits. Exists so a test can assert the
 * invariant directly instead of restating the formula.
 */
export function overflowAfterPull({
  free,
  joinGap,
  runHeight,
}: FitMeasurements): number {
  return joinGap + runHeight - free;
}

/**
 * Free space as the pre-fix engine computed it: total usable height minus the
 * span from the first block's top to the last block's bottom.
 *
 * Kept only so the regression test can demonstrate what was wrong with it. A
 * span starts at the first block's border-box top, so any margin ABOVE the
 * first block is invisible to it — `.section-block` and `.instruction-block`
 * each carry 10px — and the result overstates the free space by exactly that
 * margin. The engine then pulled a block into space that did not exist.
 */
export function derivedFreeSpace({
  usableHeight,
  contentSpan,
}: {
  usableHeight: number;
  contentSpan: number;
}): number {
  return usableHeight - contentSpan;
}
