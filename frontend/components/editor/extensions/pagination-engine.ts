import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "prosemirror-state";
import type { EditorView } from "prosemirror-view";
import { createPageId } from "../pagination-utils";
import { canPullUp } from "./pagination-fit";

const paginationKey = new PluginKey("paginationEngine");

type PageEntry = {
  node: any;
  pos: number;
};

/**
 * Blocks that must never be the last thing on a page.
 *
 * A section heading stranded at the bottom with its questions overleaf is the
 * classic widow, and the previous engine produced it in both directions: the
 * split path pushed the heading down, the pull-up path dragged it back alone.
 * Treating a heading as glued to what follows it — a "keep-together run" —
 * removes the oscillation and is what lets a section start mid-page whenever
 * its heading and first question genuinely fit.
 */
const KEEP_WITH_NEXT = new Set([
  "sectionBlock",
  "instructionBlock",
  "paperHeaderBlock",
]);

// Fit is decided against the space actually left on the page
// (`remainingSpace`) and the gap the incoming block will actually open
// (`joinGap`) — both measured from the live layout. The arithmetic lives in
// pagination-fit.ts so it can be tested without a browser.

function getPageEntries(doc: any): PageEntry[] {
  const pages: PageEntry[] = [];
  doc.descendants((node: any, pos: number) => {
    if (node.type?.name === "page") {
      pages.push({ node, pos });
    }
  });
  return pages;
}

function isPageEmpty(pageNode: any) {
  if (!pageNode || pageNode.childCount === 0) return true;

  for (let i = 0; i < pageNode.childCount; i += 1) {
    const child = pageNode.child(i);
    if (child.type?.name === "pageBreak") continue;

    if (child.isTextblock) {
      if ((child.textContent || "").trim().length > 0) return false;
      continue;
    }

    return false;
  }

  return true;
}

function getChildOffset(node: any, index: number) {
  let offset = 0;
  for (let i = 0; i < index; i += 1) {
    offset += node.child(i).nodeSize;
  }
  return offset;
}

function findPageBreakIndex(pageNode: any) {
  for (let i = 0; i < pageNode.childCount; i += 1) {
    if (pageNode.child(i).type?.name === "pageBreak") {
      return i;
    }
  }
  return -1;
}

// ── Measurement ─────────────────────────────────────────────────────────

/**
 * The usable height inside a page's content box.
 *
 * `clientHeight` includes padding, so the padding has to come back off to get
 * the height content can actually occupy (A4 here: 1121 − 48 − 56 = 1017px).
 * Used only to decide whether a block could EVER share a page with a heading;
 * fit decisions measure the live page directly (see `remainingSpace`).
 */
function usableHeight(contentEl: HTMLElement) {
  const style = window.getComputedStyle(contentEl);
  const paddingTop = parseFloat(style.paddingTop) || 0;
  const paddingBottom = parseFloat(style.paddingBottom) || 0;
  return contentEl.clientHeight - paddingTop - paddingBottom;
}

/** Where content must stop — the bottom of the content box, not the border box. */
function contentBottom(contentEl: HTMLElement) {
  const style = window.getComputedStyle(contentEl);
  const paddingBottom = parseFloat(style.paddingBottom) || 0;
  return contentEl.getBoundingClientRect().bottom - paddingBottom;
}

/**
 * Unused vertical space below the last block on a page.
 *
 * Measured directly — bottom of the content box minus bottom of the last
 * child — rather than derived as `usableHeight − contentHeight`. The derived
 * form silently assumes content begins exactly at the content-box top, and it
 * does not: `.section-block` and `.instruction-block` each carry a 10px top
 * margin, so a page opening with either has 10px that the derivation cannot
 * see. The pull-up rule was therefore allowed to fill 10px past the real
 * bottom, the split rule immediately pushed the block back, and the two rules
 * fought each other until the pass ceiling stopped pagination mid-document —
 * leaving pages half empty. Measuring the gap that actually exists makes the
 * two rules exact inverses, so a pulled-up block can never overflow.
 */
function remainingSpace(contentEl: HTMLElement, children: HTMLElement[]) {
  if (children.length === 0) return usableHeight(contentEl);
  const lastBottom = children[children.length - 1].getBoundingClientRect().bottom;
  return contentBottom(contentEl) - lastBottom;
}

/**
 * Height actually occupied by children `[from, to)`, margins between included.
 *
 * Measured as a span rather than a sum: the distance from the top of the first
 * block to the bottom of the last block necessarily contains the margins
 * collapsed between them, which summing individual heights does not. The
 * leading margin above `from` is excluded by construction — `joinGap` accounts
 * for it separately, because whether it applies depends on what it lands next
 * to.
 */
function spanHeight(children: HTMLElement[], from: number, to: number) {
  if (from >= to || from < 0 || to > children.length) return 0;
  const top = children[from].getBoundingClientRect().top;
  const bottom = children[to - 1].getBoundingClientRect().bottom;
  return Math.max(0, bottom - top);
}

function marginTop(el: HTMLElement) {
  return parseFloat(window.getComputedStyle(el).marginTop) || 0;
}

function marginBottom(el: HTMLElement) {
  return parseFloat(window.getComputedStyle(el).marginBottom) || 0;
}

/**
 * The gap that will open up when `incoming` is appended after `previous`.
 *
 * Adjacent siblings collapse their facing margins to the larger of the two, so
 * this is exactly `max(previous.margin-bottom, incoming.margin-top)` — not a
 * guess, and not the widest gap found elsewhere on the page (which is what the
 * previous heuristic used, over-budgeting by up to a line on any page that
 * happened to contain a section heading).
 */
function joinGap(previous: HTMLElement | undefined, incoming: HTMLElement) {
  const incomingTop = marginTop(incoming);
  if (!previous) return incomingTop;
  return Math.max(marginBottom(previous), incomingTop);
}

/**
 * The first child that spills past the usable content area.
 *
 * The previous implementation walked backwards and returned the first hit,
 * which is the LAST overflowing child — almost always `childCount - 1`. The
 * page was then split one block at a time across many animation frames, and
 * because each pass re-ran `adjustSplitIndex` independently it could shave off
 * more than it needed to. Returning the first overflowing index splits the
 * page correctly in a single transaction.
 *
 * The limit is the content-box bottom. The old code used the border-box bottom
 * plus a pixel, which is a whole 56px of bottom padding too generous, so a
 * block could sit in the page margin and be reported as fitting.
 */
function findOverflowIndex(contentEl: HTMLElement) {
  const children = Array.from(contentEl.children) as HTMLElement[];
  const maxBottom = contentBottom(contentEl);

  for (let i = 0; i < children.length; i += 1) {
    if (children[i].getBoundingClientRect().bottom > maxBottom + 1) {
      return i;
    }
  }

  return null;
}

// ── Keep-together ───────────────────────────────────────────────────────

/**
 * How many children starting at `index` form one indivisible run.
 *
 * A section heading (optionally followed by its instruction block) plus the
 * first block after it. Everything else is a run of one.
 */
function keepTogetherRun(pageNode: any, index: number) {
  let end = index;
  while (
    end < pageNode.childCount - 1 &&
    KEEP_WITH_NEXT.has(pageNode.child(end).type?.name)
  ) {
    end += 1;
  }
  return end - index + 1;
}

/**
 * Pull a split point back so it never lands inside a keep-together run.
 *
 * Walking backwards from the proposed index: while the block just before the
 * split is one that must stay with what follows, move the split above it. The
 * guard against returning 0 matters — splitting at 0 would move the entire
 * page's content and leave an empty page behind, which the engine would then
 * delete, looping forever.
 */
function adjustSplitIndex(pageNode: any, splitIndex: number) {
  if (splitIndex <= 0 || splitIndex >= pageNode.childCount) return splitIndex;

  let index = splitIndex;
  while (index > 0 && KEEP_WITH_NEXT.has(pageNode.child(index - 1).type?.name)) {
    index -= 1;
  }

  return index > 0 ? index : splitIndex;
}

// ── Transactions ────────────────────────────────────────────────────────

function splitPageAtIndex(state: any, pagePos: number, pageNode: any, splitIndex: number) {
  if (splitIndex < 0 || splitIndex >= pageNode.childCount) return null;

  const tr = state.tr;
  const contentStart = pagePos + 1;
  const from = contentStart + getChildOffset(pageNode, splitIndex);
  const to = contentStart + pageNode.content.size;
  const slice = state.doc.slice(from, to);

  if (slice.size === 0) return null;

  tr.delete(from, to);

  const insertPos = tr.mapping.map(pagePos + pageNode.nodeSize);
  const nextPage = tr.doc.nodeAt(insertPos);

  if (nextPage && nextPage.type?.name === "page") {
    tr.insert(insertPos + 1, slice.content);
  } else {
    const newPage = pageNode.type.create(
      { pageId: createPageId() },
      slice.content,
    );
    tr.insert(insertPos, newPage);
  }

  return tr;
}

/**
 * Move the first `count` blocks of the next page onto the end of this one.
 *
 * Moving a whole run rather than a single block is what allows a section to
 * begin part-way down a page: the heading and its first question travel
 * together or not at all.
 */
function moveLeadingBlocksToPreviousPage(
  state: any,
  pagePos: number,
  pageNode: any,
  nextPagePos: number,
  nextPageNode: any,
  count: number,
) {
  if (!nextPageNode || nextPageNode.childCount === 0) return null;
  const take = Math.min(count, nextPageNode.childCount);
  if (take <= 0) return null;

  const tr = state.tr;
  const from = nextPagePos + 1;
  let size = 0;
  for (let i = 0; i < take; i += 1) {
    size += nextPageNode.child(i).nodeSize;
  }
  const to = from + size;
  const slice = state.doc.slice(from, to);

  if (slice.size === 0) return null;

  tr.delete(from, to);

  const insertPos = pagePos + 1 + pageNode.content.size;
  tr.insert(insertPos, slice.content);

  const mappedNextPagePos = tr.mapping.map(nextPagePos);
  const updatedNextPage = tr.doc.nodeAt(mappedNextPagePos);

  if (
    updatedNextPage &&
    updatedNextPage.type?.name === "page" &&
    updatedNextPage.childCount === 0
  ) {
    tr.delete(mappedNextPagePos, mappedNextPagePos + updatedNextPage.nodeSize);
  }

  return tr;
}

// ── One pass ────────────────────────────────────────────────────────────

function paginateOnce(view: EditorView) {
  const { state } = view;
  const pages = getPageEntries(state.doc);

  if (pages.length > 1) {
    const lastPage = pages[pages.length - 1];
    if (isPageEmpty(lastPage.node)) {
      const tr = state.tr;
      tr.delete(lastPage.pos, lastPage.pos + lastPage.node.nodeSize);
      return tr;
    }
  }

  for (let i = 0; i < pages.length; i += 1) {
    const { node: pageNode, pos: pagePos } = pages[i];
    const pageDom = view.nodeDOM(pagePos) as HTMLElement | null;
    if (!pageDom) continue;

    if (!pageNode.attrs?.pageId) {
      const tr = state.tr.setNodeMarkup(pagePos, undefined, {
        ...pageNode.attrs,
        pageId: createPageId(),
      });
      return tr;
    }

    const contentEl = pageDom.querySelector(
      '[data-page-content="true"]',
    ) as HTMLElement | null;

    if (!contentEl) continue;
    if (contentEl.clientHeight === 0) continue;

    const breakIndex = findPageBreakIndex(pageNode);
    if (breakIndex !== -1) {
      if (breakIndex < pageNode.childCount - 1) {
        return splitPageAtIndex(state, pagePos, pageNode, breakIndex + 1);
      }

      if (breakIndex === pageNode.childCount - 1 && !pages[i + 1]) {
        const tr = state.tr;
        const insertPos = pagePos + pageNode.nodeSize;
        const newPage = pageNode.type.createAndFill({
          pageId: createPageId(),
        });
        if (newPage) {
          tr.insert(insertPos, newPage);
          return tr;
        }
      }
    }

    const children = Array.from(contentEl.children) as HTMLElement[];
    const available = usableHeight(contentEl);

    // ── Overflow: this page holds more than it can show ─────────────────
    const overflows =
      contentEl.scrollHeight > contentEl.clientHeight ||
      (children.length > 0 &&
        children[children.length - 1].getBoundingClientRect().bottom >
          contentBottom(contentEl) + 1);

    if (overflows) {
      const overflowIndex = findOverflowIndex(contentEl);
      const proposed =
        overflowIndex !== null && overflowIndex > 0
          ? overflowIndex
          : pageNode.childCount - 1;

      // The keep-together adjustment now applies to the fallback path too.
      // Previously it did not, so when `findOverflowIndex` came back null the
      // engine blind-split the last block and could strand a section heading.
      const safeIndex = adjustSplitIndex(pageNode, proposed);
      if (safeIndex > 0 && safeIndex < pageNode.childCount) {
        return splitPageAtIndex(state, pagePos, pageNode, safeIndex);
      }

      // A single block taller than a whole page. Nothing to split; leave it
      // rather than loop.
      continue;
    }

    // ── Underflow: can the next page's opening run move up? ─────────────
    const nextPage = pages[i + 1];
    if (!nextPage) continue;

    if (
      pageNode.childCount > 0 &&
      pageNode.lastChild?.type?.name === "pageBreak"
    ) {
      continue;
    }

    const nextPageDom = view.nodeDOM(nextPage.pos) as HTMLElement | null;
    const nextContentEl = nextPageDom?.querySelector(
      '[data-page-content="true"]',
    ) as HTMLElement | null;
    if (!nextContentEl) continue;

    const nextChildren = Array.from(nextContentEl.children) as HTMLElement[];
    if (nextChildren.length === 0) continue;

    // How many of the next page's opening blocks are glued together. A section
    // heading brings its first question with it; anything else moves alone.
    let runLength = Math.min(
      keepTogetherRun(nextPage.node, 0),
      nextChildren.length,
    );

    const gap = joinGap(children[children.length - 1], nextChildren[0]);
    const free = remainingSpace(contentEl, children);

    // A run whose non-heading tail cannot fit on an EMPTY page — a full-page
    // reading passage, say — can never be kept with its heading by any page
    // break. Holding the heading back for it strands the heading at the top of
    // the next page and leaves this one short for nothing, so in that case the
    // heading travels on its own. Without this the run stays permanently
    // unmovable and the gap before every such section is a whole page.
    if (runLength > 1 && spanHeight(nextChildren, 0, runLength) > available) {
      // Drop the trailing non-heading block; what is left is the heading (and
      // its instruction block), which by construction is all that precedes it.
      runLength -= 1;
    }

    const fits = canPullUp({
      free,
      joinGap: gap,
      runHeight: spanHeight(nextChildren, 0, runLength),
    });
    if (!fits) continue;

    // Moving the run must not leave the next page starting on a widow of its
    // own — if what remains there begins with a heading whose question we just
    // took, take the heading too on the following pass (the run recomputes).
    const tr = moveLeadingBlocksToPreviousPage(
      state,
      pagePos,
      pageNode,
      nextPage.pos,
      nextPage.node,
      runLength,
    );
    if (tr) return tr;
  }

  return null;
}

export const PaginationEngine = Extension.create({
  name: "paginationEngine",

  addProseMirrorPlugins() {
    let viewRef: EditorView | null = null;
    let rafId: number | null = null;
    let isDispatching = false;
    let resizeObserver: ResizeObserver | null = null;
    let passCount = 0;

    /**
     * Ceiling on consecutive layout passes.
     *
     * Pagination is a feedback loop — every transaction changes the layout the
     * next pass measures — so a disagreement between the split and pull-up
     * rules could in principle ping-pong forever and peg a CPU. That is now
     * prevented at the source: fit is decided against measured space, making
     * the two rules exact inverses (see pagination-fit.ts and its test), so
     * this is purely a hang guard and can afford to be generous. One pass per
     * animation frame settles even a long answer script in a few hundred.
     *
     * Hitting it is a bug, not a slow document — so it says so, once. Silently
     * stopping is what made the last measurement bug so hard to place: the
     * document simply stayed half laid out with pages ending early.
     */
    const MAX_PASSES = 1200;
    let warnedAboutCap = false;

    const schedule = (reset = false) => {
      if (!viewRef || viewRef.isDestroyed) return;
      if (reset) {
        passCount = 0;
        warnedAboutCap = false;
      }
      if (rafId !== null) cancelAnimationFrame(rafId);

      rafId = window.requestAnimationFrame(() => {
        rafId = null;
        if (!viewRef || viewRef.isDestroyed) return;
        if (passCount >= MAX_PASSES) {
          if (!warnedAboutCap) {
            warnedAboutCap = true;
            console.warn(
              `[pagination] gave up after ${MAX_PASSES} passes — page breaks ` +
                `below this point may be wrong. This means two layout rules ` +
                `disagree; check pagination-fit.ts against the block margins ` +
                `in styles/editor.css.`,
            );
          }
          return;
        }
        passCount += 1;

        const tr = paginateOnce(viewRef);
        if (!tr || !tr.docChanged) return;

        // try/finally: a throw here used to leave `isDispatching` stuck true,
        // which permanently muted the plugin's own update handler — pagination
        // would stop for the rest of the session with no indication why.
        isDispatching = true;
        try {
          tr.setMeta(paginationKey, true);
          viewRef.dispatch(tr);
        } finally {
          isDispatching = false;
        }

        schedule();
      });
    };

    return [
      new Plugin({
        key: paginationKey,
        view(view) {
          viewRef = view;
          schedule(true);

          if (typeof ResizeObserver !== "undefined") {
            resizeObserver = new ResizeObserver(() => schedule(true));
            resizeObserver.observe(view.dom);
          }

          return {
            update(view, prevState) {
              if (isDispatching) return;
              if (!view.state.doc.eq(prevState.doc)) {
                schedule(true);
              }
            },
            destroy() {
              if (rafId !== null) cancelAnimationFrame(rafId);
              resizeObserver?.disconnect();
              resizeObserver = null;
              viewRef = null;
            },
          };
        },
      }),
    ];
  },
});
