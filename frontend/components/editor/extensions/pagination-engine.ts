import { Extension } from "@tiptap/core";
import type { Editor } from "@tiptap/core";
import { Plugin, PluginKey } from "prosemirror-state";
import type { EditorView } from "prosemirror-view";
import { createPageId } from "../pagination-utils";
import { canPullUp } from "./pagination-fit";

const paginationKey = new PluginKey("paginationEngine");

type PaginationStorage = {
  /** Set while the plugin view is alive; asks for one more layout pass. */
  requestPass: (() => void) | null;
};

/**
 * Ask the engine to re-measure, for a layout change the document cannot see.
 *
 * The plugin re-runs on every doc change, which covers editing. It cannot cover
 * content that changes size *after* it is in the document — an <img> that has
 * not decoded yet, a webfont swapping in — because none of that is a
 * transaction. Those call sites use this.
 *
 * Note this is deliberately NOT "dispatch an empty transaction": the plugin's
 * update handler only schedules when `doc.eq(prevDoc)` is false, so a
 * meta-only transaction changes nothing and is ignored.
 */
export function requestRepagination(editor: Editor | null | undefined) {
  const storage = (
    editor?.storage as Record<string, PaginationStorage | undefined> | undefined
  )?.paginationEngine;
  storage?.requestPass?.();
}

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
function findOverflowIndex(blocks: HTMLElement[], contentEl: HTMLElement) {
  const maxBottom = contentBottom(contentEl);

  for (let i = 0; i < blocks.length; i += 1) {
    if (blocks[i].getBoundingClientRect().bottom > maxBottom + 1) {
      return i;
    }
  }

  return null;
}

/**
 * The DOM element rendering each of a page's block children, in order.
 *
 * This exists because `contentEl.children` is NOT the blocks, and every
 * measurement that assumed it was has been quietly wrong. A page is a React
 * NodeView whose `<NodeViewContent />` renders a `div[data-node-view-content]`,
 * and TipTap then appends its own `div[data-node-view-content-react]` inside
 * that as the real ProseMirror `contentDOM` (@tiptap/react ~806-810). So
 * `.doc-page-content` has exactly ONE child — a wrapper — however many
 * questions the page holds.
 *
 * The engine read that single wrapper as if it were the block list, which put
 * the DOM out of step with the ProseMirror node indices it was reasoning
 * about. `spanHeight(nextChildren, 0, 1)` then measured the whole of the next
 * page instead of just its first block, so the pull-up rule compared an entire
 * page against the space left on the previous one and refused essentially
 * every time — which is why a short page kept its hole instead of drawing the
 * next question up. The same collapse capped `runLength` at 1, disabling
 * keep-together, and made `findOverflowIndex` degrade to "split off the last
 * block", one block per animation frame (hence a 1200-pass ceiling for what
 * should take a handful).
 *
 * Resolving each child through `view.nodeDOM(pos)` — ProseMirror's own node →
 * DOM map — guarantees `blocks[i]` renders `pageNode.child(i)` no matter how
 * many wrappers a node view introduces, so it cannot drift again.
 */
function getBlockElements(view: EditorView, pageNode: any, pagePos: number) {
  const blocks: HTMLElement[] = [];
  const contentStart = pagePos + 1;
  let offset = 0;

  for (let i = 0; i < pageNode.childCount; i += 1) {
    const dom = view.nodeDOM(contentStart + offset);
    if (!(dom instanceof HTMLElement)) return null;
    blocks.push(styledBlockElement(dom));
    offset += pageNode.child(i).nodeSize;
  }

  return blocks;
}

/**
 * The element that actually carries a block's styles.
 *
 * `nodeDOM` hands back a React node view's outer `div.react-renderer`, which
 * is an unstyled box wrapping the `NodeViewWrapper` element that holds the
 * real class (`.question-block`, `.section-block`, …). Heights are identical
 * either way — the wrapper has no border or padding, so the two border boxes
 * coincide — but *margins* are not: the inner element's margins collapse
 * straight through the wrapper, and `getComputedStyle` reports the collapsed-
 * through margin as 0 on the outer box. Measuring there would make `joinGap`
 * return nothing for exactly the blocks whose 10px margins it exists to
 * account for. Nodes rendered from `renderHTML` rather than a React node view
 * have no wrapper and are returned unchanged.
 */
function styledBlockElement(dom: HTMLElement): HTMLElement {
  const inner = dom.firstElementChild;
  if (
    dom.classList.contains("react-renderer") &&
    inner instanceof HTMLElement &&
    inner.hasAttribute("data-node-view-wrapper")
  ) {
    return inner;
  }
  return dom;
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
  const splitPos = contentStart + getChildOffset(pageNode, splitIndex);

  const nextPagePos = pagePos + pageNode.nodeSize;
  const nextPage = state.doc.nodeAt(nextPagePos);

  if (nextPage && nextPage.type?.name === "page") {
    // Join with the next page to combine their blocks seamlessly
    tr.join(nextPagePos);
    // Split at the target position, preserving the next page's original attributes
    tr.split(splitPos, 1, [{ type: pageNode.type, attrs: nextPage.attrs }]);
  } else {
    // If there is no next page, just split to create a new one
    tr.split(splitPos, 1, [{ type: pageNode.type, attrs: { pageId: createPageId() } }]);
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
  let size = 0;
  for (let i = 0; i < take; i += 1) {
    size += nextPageNode.child(i).nodeSize;
  }

  // Join the two pages together (removes the `</page><page>` tags, which are size 2)
  tr.join(nextPagePos);

  // If we aren't pulling the entire page, we need to split it again to recreate the boundary
  if (take < nextPageNode.childCount) {
    // The original boundary was after the first `size` tokens in the next page.
    // Because we deleted the 2 boundary tokens at nextPagePos, the new split position is shifted by -2.
    const splitPos = nextPagePos - 1 + size;
    tr.split(splitPos, 1, [{ type: nextPageNode.type, attrs: nextPageNode.attrs }]);
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

    const children = getBlockElements(view, pageNode, pagePos);
    if (!children) continue;
    const available = usableHeight(contentEl);

    // ── Overflow: this page holds more than it can show ─────────────────
    const overflows =
      contentEl.scrollHeight > contentEl.clientHeight ||
      (children.length > 0 &&
        children[children.length - 1].getBoundingClientRect().bottom >
          contentBottom(contentEl) + 1);

    if (overflows) {
      const overflowIndex = findOverflowIndex(children, contentEl);
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

    const nextChildren = getBlockElements(view, nextPage.node, nextPage.pos);
    if (!nextChildren || nextChildren.length === 0) continue;

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

  addStorage(): PaginationStorage {
    return { requestPass: null };
  },

  addProseMirrorPlugins() {
    const storage = this.storage as PaginationStorage;
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
     *
     * It counts passes *since the layout last settled*, not since the last user
     * edit. That distinction is what makes it safe for the resize observer
     * below to schedule work: an observer-driven pass must not reset the guard
     * (an oscillation would then loop forever with the guard disabled), but it
     * also must not inherit a count run up hours ago by an unrelated edit. A
     * pass that produces no transaction means the document is stable, which is
     * the only honest place to zero the counter.
     */
    const MAX_PASSES = 1200;
    let warnedAboutCap = false;

    /**
     * Blocks currently watched for a size change, and the height each had when
     * we last looked.
     *
     * `observe()` delivers one callback immediately with the element's current
     * size. Recording the height at observe time makes that first callback a
     * no-op instead of a scheduled pass, which is what stops re-syncing the
     * observed set from feeding itself.
     */
    const observedBlocks = new Set<Element>();
    const lastHeight = new WeakMap<Element, number>();

    /**
     * Watch each page's content wrapper for a height change.
     *
     * The observer used to be attached to `view.dom` alone, where it could
     * essentially never fire: `.doc-page` is a fixed 1123px box and
     * `.doc-page-content` is `height: 100%; overflow: hidden` (styles/editor.css),
     * so anything growing or shrinking *inside* a page leaves the editor root
     * exactly the same height. The one thing that did move it was the page
     * count — which only changes as a result of the engine's own work. So the
     * engine had no signal for the case it most needed one: content that
     * changes size without changing the document.
     *
     * That is why a freshly generated image left a hole. It is inserted at zero
     * height (an <img> with `height: auto` and no intrinsic size yet), the page
     * is laid out around a block that is not there, and when the bytes arrive
     * and the block takes its real height nothing tells the engine to look
     * again.
     *
     * The single child of `.doc-page-content` is the node-view content wrapper
     * (see `getBlockElements` for why it is a wrapper and not the blocks). That
     * is the ideal thing to observe here: it is unconstrained in height, so it
     * tracks the page's true content extent even though its fixed-height parent
     * clips it — and it is one observation per page rather than one per
     * question.
     */
    const syncObservedBlocks = () => {
      if (!resizeObserver || !viewRef || viewRef.isDestroyed) return;

      const wanted = new Set<Element>();
      viewRef.dom
        .querySelectorAll('[data-page-content="true"]')
        .forEach((contentEl) => {
          for (const child of Array.from(contentEl.children)) {
            wanted.add(child);
          }
        });

      for (const el of observedBlocks) {
        if (!wanted.has(el)) {
          resizeObserver.unobserve(el);
          observedBlocks.delete(el);
        }
      }

      for (const el of wanted) {
        if (observedBlocks.has(el)) continue;
        lastHeight.set(el, el.getBoundingClientRect().height);
        resizeObserver.observe(el);
        observedBlocks.add(el);
      }
    };

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
        if (!tr || !tr.docChanged) {
          // Settled. Zero the hang guard and re-point the observer at the
          // blocks that now exist — this is the only moment the DOM is known
          // to be stable, so it is the only moment worth snapshotting.
          passCount = 0;
          warnedAboutCap = false;
          syncObservedBlocks();
          return;
        }

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
          storage.requestPass = () => schedule();
          schedule(true);

          if (typeof ResizeObserver !== "undefined") {
            resizeObserver = new ResizeObserver((entries) => {
              let moved = false;

              for (const entry of entries) {
                const height = entry.target.getBoundingClientRect().height;
                const previous = lastHeight.get(entry.target);
                lastHeight.set(entry.target, height);
                // Sub-pixel jitter is not a layout change. Anything larger is.
                if (previous === undefined || Math.abs(previous - height) > 0.5) {
                  moved = true;
                }
              }

              // No `reset`: an observer firing on the engine's own output must
              // not clear the hang guard. See MAX_PASSES.
              if (moved) schedule();
            });

            syncObservedBlocks();
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
              observedBlocks.clear();
              storage.requestPass = null;
              viewRef = null;
            },
          };
        },
      }),
    ];
  },
});
