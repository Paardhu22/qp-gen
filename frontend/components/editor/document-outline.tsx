"use client";

/**
 * The document panel — the left rail of a word processor.
 *
 * What used to live on this side was paper *setup*: the generator sidebar, and
 * after that the button that opened it. That is backwards for an editor. The
 * left of a document window belongs to the document — in Google Docs it is
 * tabs and the outline, in Word it is the navigation pane, in Pages it is page
 * thumbnails. Setup moved to the right (`generate-dock.tsx`), and this shows
 * what is actually on the page.
 *
 * ## Two things, in the order Docs puts them
 *
 * 1. **Document tabs.** This app already has them — Sets A/B/C from one
 *    generation. They used to be a strip of underlined buttons above the page,
 *    which is the shape of a *filter*, not of parallel documents. As a list of
 *    named tabs they read the way they behave.
 * 2. **Outline.** Section headers and headings, grouped by the page they fall
 *    on, so the panel doubles as the "preview of the contents" a long paper
 *    needs. Clicking one scrolls to it.
 *
 * ## Why the outline is read from the DOM, not from the document JSON
 *
 * The store already holds `pages` (`extractPagesFromDoc`), and deriving titles
 * from that JSON would be the obvious move. But an outline entry has to
 * *scroll to something*, and mapping a JSON node back to its rendered element
 * means re-walking the same DOM anyway — with the extra risk that the two
 * walks disagree after a pagination pass and the panel scrolls to the wrong
 * heading. So `pages` is used purely as a change signal (it is already
 * debounced at 250 ms in the editor) and the entries themselves come from one
 * pass over the rendered pages. Elements are re-queried at click time rather
 * than held, because ProseMirror replaces nodes on re-render and a stored
 * reference can quietly go detached.
 */

import * as React from "react";
import { FileText, PanelLeftClose, PanelLeftOpen } from "lucide-react";

import { cn } from "@/lib/utils";
import { useEditorStore } from "@/store/editor-store";

export interface DocumentTab {
  id: string;
  label: string;
}

interface Props {
  /** Set tabs. Always at least one, so the panel is never blank. */
  tabs: DocumentTab[];
  activeTab: string;
  onSelectTab: (id: string) => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface OutlineEntry {
  /** Position in the collected list — how the element is found again. */
  index: number;
  text: string;
  /** 0 = section header, 1..3 = heading levels. Drives indentation only. */
  level: number;
  page: number;
}

/** Section blocks first-class; headings for hand-written papers. */
const OUTLINE_SELECTOR = ".section-block, h1, h2, h3";

/**
 * Every outline-worthy element, in document order, with the page it sits on.
 *
 * One function for both collection and lookup so an entry's `index` can never
 * mean something different to the two callers.
 */
function collectOutline(): { entries: OutlineEntry[]; elements: HTMLElement[] } {
  const entries: OutlineEntry[] = [];
  const elements: HTMLElement[] = [];

  if (typeof document === "undefined") return { entries, elements };
  const root = document.getElementById("tiptap-paper-container");
  if (!root) return { entries, elements };

  const pages = Array.from(root.querySelectorAll<HTMLElement>(".doc-page"));
  pages.forEach((page, pageIndex) => {
    page.querySelectorAll<HTMLElement>(OUTLINE_SELECTOR).forEach((element) => {
      const isSection = element.classList.contains("section-block");
      // A section block renders its title next to a computed summary
      // ("(6 × 1 = 6)"). The outline wants the title alone.
      const source = isSection
        ? (element.querySelector<HTMLElement>(".section-title") ?? element)
        : element;
      const text = (source.textContent || "").replace(/\s+/g, " ").trim();
      if (!text) return;

      entries.push({
        index: elements.length,
        text,
        level: isSection ? 0 : Number(element.tagName.slice(1)) || 1,
        page: pageIndex + 1,
      });
      elements.push(element);
    });
  });

  return { entries, elements };
}

export function DocumentOutline({
  tabs,
  activeTab,
  onSelectTab,
  open,
  onOpenChange,
}: Props) {
  // `pages` is the signal, not the source — see the note at the top.
  const pages = useEditorStore((state) => state.pages);
  const [entries, setEntries] = React.useState<OutlineEntry[]>([]);
  const [activeIndex, setActiveIndex] = React.useState<number | null>(null);

  // Recollect after the browser has laid the document out. `pages` lands from
  // a debounce inside the editor, but pagination can still be mid-flight when
  // it does, so a frame is allowed to pass first.
  React.useEffect(() => {
    if (!open) return;
    let frame = 0;
    frame = requestAnimationFrame(() => {
      setEntries(collectOutline().entries);
    });
    return () => cancelAnimationFrame(frame);
  }, [pages, open, activeTab]);

  // Scroll spy. The nearest entry at or above the top of the viewport wins,
  // which is what makes the panel track reading position rather than lag a
  // whole page behind it.
  React.useEffect(() => {
    if (!open || entries.length === 0) return;
    const container = document.querySelector<HTMLElement>("[data-editor-scroll]");
    if (!container) return;

    let frame = 0;
    const measure = () => {
      frame = 0;
      const { elements } = collectOutline();
      if (elements.length === 0) return;
      const top = container.getBoundingClientRect().top + 96;
      let current: number | null = null;
      elements.forEach((element, index) => {
        if (element.getBoundingClientRect().top <= top) current = index;
      });
      setActiveIndex(current ?? 0);
    };

    const onScroll = () => {
      if (frame) return;
      frame = requestAnimationFrame(measure);
    };

    measure();
    container.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      container.removeEventListener("scroll", onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [open, entries.length]);

  const goTo = React.useCallback((index: number) => {
    const { elements } = collectOutline();
    const element = elements[index];
    if (!element) return;
    element.scrollIntoView({ behavior: "smooth", block: "start" });
    setActiveIndex(index);
  }, []);

  const pageCount = pages.length;

  if (!open) {
    return (
      <div className="hidden w-12 flex-shrink-0 flex-col items-center gap-1 border-r border-border bg-background py-2 lg:flex print:hidden">
        <button
          type="button"
          onClick={() => onOpenChange(true)}
          title="Show document panel"
          aria-label="Show document panel"
          className="flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <PanelLeftOpen className="h-[18px] w-[18px]" />
        </button>
      </div>
    );
  }

  return (
    <aside className="hidden w-60 flex-shrink-0 flex-col border-r border-border bg-background lg:flex print:hidden xl:w-64">
      {/* Header. The way back to just the page, and nothing else — the
          document's name already has its own row above the toolbar, and
          repeating it here would spend the panel's most valuable line on
          something the eye has just read. */}
      <div className="flex h-11 flex-shrink-0 items-center px-2">
        <button
          type="button"
          onClick={() => onOpenChange(false)}
          title="Hide document panel"
          aria-label="Hide document panel"
          className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <PanelLeftClose className="h-[18px] w-[18px]" />
        </button>
      </div>

      <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto px-2 pb-6">
        {/* ── Document tabs ─────────────────────────────────────────── */}
        <p className="px-2 pb-1.5 pt-2 text-[13px] font-medium text-foreground">
          Document tabs
        </p>
        <ul className="space-y-0.5">
          {tabs.map((tab) => {
            const active = tab.id === activeTab;
            return (
              <li key={tab.id}>
                <button
                  type="button"
                  onClick={() => onSelectTab(tab.id)}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-full px-3 py-1.5 text-left text-[13px] transition-colors",
                    active
                      ? "bg-primary/10 font-medium text-foreground"
                      : "text-muted-foreground hover:bg-muted",
                  )}
                >
                  <FileText
                    className={cn(
                      "h-4 w-4 flex-shrink-0",
                      active ? "text-primary" : "text-muted-foreground",
                    )}
                  />
                  <span className="truncate">{tab.label}</span>
                </button>
              </li>
            );
          })}
        </ul>

        {/* ── Outline ───────────────────────────────────────────────── */}
        <div className="mt-5 border-t border-border pt-3">
          <div className="flex items-baseline justify-between gap-2 px-2 pb-1.5">
            <p className="text-[13px] font-medium text-foreground">Outline</p>
            {pageCount > 0 ? (
              <span className="text-[11px] tabular-nums text-muted-foreground">
                {pageCount} page{pageCount === 1 ? "" : "s"}
              </span>
            ) : null}
          </div>

          {entries.length === 0 ? (
            <p className="px-2 py-1 text-[12px] italic leading-relaxed text-muted-foreground">
              Sections and headings you add to the document will appear here.
            </p>
          ) : (
            <ul className="space-y-px">
              {entries.map((entry, i) => {
                const startsPage = i === 0 || entries[i - 1].page !== entry.page;
                return (
                  <React.Fragment key={`${entry.index}-${entry.text}`}>
                    {startsPage ? (
                      <li
                        className={cn(
                          "px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70",
                          i === 0 ? "pt-1" : "pt-3",
                        )}
                      >
                        Page {entry.page}
                      </li>
                    ) : null}
                    <li>
                      <button
                        type="button"
                        onClick={() => goTo(entry.index)}
                        title={entry.text}
                        className={cn(
                          "block w-full truncate rounded px-2 py-1 text-left text-[13px] transition-colors",
                          entry.level === 0
                            ? "font-medium"
                            : "font-normal",
                          activeIndex === entry.index
                            ? "bg-muted text-foreground"
                            : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                        )}
                        style={{
                          paddingLeft: `${8 + entry.level * 12}px`,
                        }}
                      >
                        {entry.text}
                      </button>
                    </li>
                  </React.Fragment>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </aside>
  );
}
