import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "prosemirror-state";
import type { EditorView } from "prosemirror-view";
import { createPageId } from "../pagination-utils";

const paginationKey = new PluginKey("paginationEngine");

type PageEntry = {
  node: any;
  pos: number;
};

function getPageEntries(doc: any): PageEntry[] {
  const pages: PageEntry[] = [];
  doc.descendants((node: any, pos: number) => {
    if (node.type?.name === "page") {
      pages.push({ node, pos });
    }
  });
  return pages;
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

function findOverflowIndex(contentEl: HTMLElement) {
  const children = Array.from(contentEl.children) as HTMLElement[];
  const containerRect = contentEl.getBoundingClientRect();
  const maxBottom = containerRect.bottom + 1;

  for (let i = children.length - 1; i >= 0; i -= 1) {
    const childRect = children[i].getBoundingClientRect();
    if (childRect.bottom > maxBottom) {
      return i;
    }
  }

  return null;
}

function adjustSplitIndex(pageNode: any, splitIndex: number) {
  if (splitIndex <= 0 || splitIndex >= pageNode.childCount) return splitIndex;

  const prevNode = pageNode.child(splitIndex - 1);
  if (prevNode?.type?.name === "sectionBlock") {
    return splitIndex - 1 > 0 ? splitIndex - 1 : splitIndex;
  }

  const prevPrevNode = splitIndex - 2 >= 0 ? pageNode.child(splitIndex - 2) : null;
  if (
    prevNode?.type?.name === "instructionBlock" &&
    prevPrevNode?.type?.name === "sectionBlock"
  ) {
    return splitIndex - 2 > 0 ? splitIndex - 2 : splitIndex;
  }

  return splitIndex;
}

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

function moveFirstBlockToPreviousPage(
  state: any,
  pagePos: number,
  pageNode: any,
  nextPagePos: number,
  nextPageNode: any,
) {
  if (!nextPageNode || nextPageNode.childCount === 0) return null;

  const tr = state.tr;
  const from = nextPagePos + 1;
  const firstChild = nextPageNode.child(0);
  const to = from + firstChild.nodeSize;
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

function paginateOnce(view: EditorView) {
  const { state } = view;
  const pages = getPageEntries(state.doc);

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

    if (contentEl.scrollHeight > contentEl.clientHeight) {
      const overflowIndex = findOverflowIndex(contentEl);
      if (overflowIndex !== null && overflowIndex > 0) {
        const safeIndex = adjustSplitIndex(pageNode, overflowIndex);
        if (safeIndex > 0) {
          return splitPageAtIndex(state, pagePos, pageNode, safeIndex);
        }
      }

      if (pageNode.childCount > 1) {
        return splitPageAtIndex(state, pagePos, pageNode, pageNode.childCount - 1);
      }

      continue;
    }

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
    const nextFirstBlock = nextContentEl?.children?.[0] as HTMLElement | null;

    if (!nextFirstBlock) continue;

    // Measure the actual cumulative height of children inside the content container.
    // We cannot use scrollHeight directly because the page has a fixed 100% height
    // during underflow, making scrollHeight equal to clientHeight.
    const computedStyle = window.getComputedStyle(contentEl);
    const paddingTop = parseFloat(computedStyle.paddingTop) || 0;
    const paddingBottom = parseFloat(computedStyle.paddingBottom) || 0;
    const availableHeight = contentEl.clientHeight - paddingTop - paddingBottom;

    const children = Array.from(contentEl.children) as HTMLElement[];
    const actualContentHeight = children.reduce((acc, child) => {
      return acc + child.getBoundingClientRect().height;
    }, 0);

    const nextFirstBlockHeight = nextFirstBlock.getBoundingClientRect().height;

    // Use a small safety buffer (12px) to account for block margins and prevent layout oscillations
    // (where a block is repeatedly pulled and then split back).
    const safetyBuffer = 12;

    if (actualContentHeight + nextFirstBlockHeight + safetyBuffer <= availableHeight) {
      return moveFirstBlockToPreviousPage(
        state,
        pagePos,
        pageNode,
        nextPage.pos,
        nextPage.node,
      );
    }
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

    const schedule = () => {
      if (!viewRef || viewRef.isDestroyed) return;
      if (rafId !== null) cancelAnimationFrame(rafId);

      rafId = window.requestAnimationFrame(() => {
        rafId = null;
        if (!viewRef || viewRef.isDestroyed) return;

        const tr = paginateOnce(viewRef);
        if (!tr || !tr.docChanged) return;

        isDispatching = true;
        tr.setMeta(paginationKey, true);
        viewRef.dispatch(tr);
        isDispatching = false;

        schedule();
      });
    };

    return [
      new Plugin({
        key: paginationKey,
        view(view) {
          viewRef = view;
          schedule();

          if (typeof ResizeObserver !== "undefined") {
            resizeObserver = new ResizeObserver(() => schedule());
            resizeObserver.observe(view.dom);
          }

          return {
            update(view, prevState) {
              if (isDispatching) return;
              if (!view.state.doc.eq(prevState.doc)) {
                schedule();
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
