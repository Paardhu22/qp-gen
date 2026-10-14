"use client";

/**
 * The floating menu that appears over a question.
 *
 * It replaces a column of small icons pinned outside every question block.
 * Those were always rendered and always present in the layout: on a 38-question
 * paper that is 38 permanent buttons sitting in the margin, and the column was
 * pushed to `right: -44px` precisely because it kept colliding with the marks
 * input it sat beside.
 *
 * A floating menu is one element, positioned against whichever question the
 * teacher is actually pointing at, and gone otherwise. The paper looks like a
 * paper until you reach for it.
 *
 * ## Why hover AND selection
 *
 * Hover is how a mouse finds this. It is not how a keyboard or a touchscreen
 * does, so the menu also opens for the question containing the caret — which
 * means tabbing through a paper and pressing the same key surfaces the same
 * actions.
 *
 * ## Why it does not close on mouse-out alone
 *
 * The menu floats above the block, so travelling to it leaves the block. A
 * naive `onMouseLeave` closes the menu on the way to clicking it. The close is
 * therefore delayed and cancelled by entering the menu itself.
 */

import * as React from "react";
import { createPortal } from "react-dom";
import { ImagePlus, RefreshCw, Replace, Trash } from "lucide-react";

import { cn } from "@/lib/utils";
import { Spinner } from "@/components/ui/spinner";

export interface QuestionMenuTarget {
  /** The DOM node of the question block the menu is anchored to. */
  element: HTMLElement;
  /** Question text, used as the subject for image generation. */
  text: string;
  /** Only generated questions have a blueprint slot to regenerate against. */
  canReplace: boolean;
  onReplace: () => void;
  /** Opens the type picker, rather than swapping straight away. */
  onChangeType: () => void;
  onDelete: () => void;
  onGenerateImage: () => void;
  replacing?: boolean;
  generatingImage?: boolean;
}

interface Props {
  target: QuestionMenuTarget | null;
  /** Keeps the menu open while the pointer is inside it. */
  onMenuEnter: () => void;
  onMenuLeave: () => void;
}

function useMenuPosition(element: HTMLElement | null, menu: React.RefObject<HTMLDivElement | null>) {
  const [position, setPosition] = React.useState<{ element: HTMLElement; top: number; left: number } | null>(null);

  React.useLayoutEffect(() => {
    const toolbar = menu.current;
    if (!element || !toolbar) return;
    const canvas = element.closest<HTMLElement>("[data-editor-scroll]");
    let frame = 0;
    const measure = () => {
      frame = 0;
      const rect = element.getBoundingClientRect();
      const bounds = canvas?.getBoundingClientRect();
      const topEdge = Math.max(0, bounds ? bounds.top + canvas!.clientTop : 0);
      const bottomEdge = Math.min(window.innerHeight, bounds ? bounds.top + canvas!.clientTop + canvas!.clientHeight : window.innerHeight);
      const leftEdge = Math.max(0, bounds ? bounds.left + canvas!.clientLeft : 0);
      const rightEdge = Math.min(window.innerWidth, bounds ? bounds.left + canvas!.clientLeft + canvas!.clientWidth : window.innerWidth);
      const visibleTop = Math.max(rect.top, topEdge);
      const visibleBottom = Math.min(rect.bottom, bottomEdge);
      const { width, height } = toolbar.getBoundingClientRect();
      // Never leave actions floating over another question or over the editor
      // toolbar after their question has left the scroll viewport.
      if (
        !element.isConnected || visibleBottom - visibleTop < 24 ||
        rect.right <= leftEdge || rect.left >= rightEdge ||
        height + 16 > bottomEdge - topEdge || width + 16 > rightEdge - leftEdge
      ) {
        setPosition(current => current === null ? current : null);
        return;
      }
      const top = Math.max(topEdge + 8, Math.min((rect.top + rect.bottom - height) / 2, bottomEdge - height - 8));
      // Use the paper's right margin when it fits, keeping the marks readable.
      // A horizontally panned phone view falls back inside the visible canvas.
      const preferredLeft = rect.right + 8 + width <= rightEdge - 8 ? rect.right + 8 : rect.right - width - 8;
      const left = Math.max(leftEdge + 8, Math.min(preferredLeft, rightEdge - width - 8));
      setPosition(current => current?.element === element && current.top === top && current.left === left ? current : { element, top, left });
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(measure); };
    measure();

    // Coalesce scroll/resize work into one layout read per frame. Only the
    // active question, canvas and single shared menu are observed.
    const observer = new ResizeObserver(schedule);
    observer.observe(element);
    observer.observe(toolbar);
    if (canvas) observer.observe(canvas);
    window.addEventListener("scroll", schedule, { capture: true, passive: true });
    window.addEventListener("resize", schedule);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("scroll", schedule, true);
      window.removeEventListener("resize", schedule);
    };
  }, [element, menu]);

  return position?.element === element ? position : null;
}

function MenuButton({
  icon: Icon,
  label,
  onClick,
  busy,
  tone = "default",
}: {
  icon: React.ElementType;
  label: string;
  onClick: () => void;
  busy?: boolean;
  tone?: "default" | "destructive";
}) {
  return (
    <button
      type="button"
      // preventDefault keeps the editor's selection intact — without it,
      // pressing a menu button blurs the caret and the action loses the
      // question it was aimed at.
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      disabled={busy}
      title={label}
      aria-label={label}
      className={cn(
        "flex size-9 shrink-0 items-center justify-center rounded-lg p-0 text-[11px] font-medium transition-colors pointer-coarse:size-11",
        "disabled:cursor-not-allowed disabled:opacity-60",
        tone === "destructive"
          ? "delete-icon-button"
          : "text-foreground hover:bg-muted",
      )}
    >
      {busy ? (
        <Spinner />
      ) : (
        <Icon className="size-4" />
      )}
    </button>
  );
}

export function QuestionHoverMenu({ target, onMenuEnter, onMenuLeave }: Props) {
  const menu = React.useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = React.useState(false);
  const element = mounted ? target?.element ?? null : null;
  const position = useMenuPosition(element, menu);

  React.useEffect(() => setMounted(true), []);

  if (!mounted || !target) return null;

  return createPortal(
    <div
      ref={menu}
      role="toolbar"
      aria-label="Question actions"
      data-question-menu="true"
      onMouseEnter={onMenuEnter}
      onMouseLeave={onMenuLeave}
      style={{
        position: "fixed",
        top: position?.top ?? 0,
        left: position?.left ?? 0,
        visibility: position ? "visible" : "hidden",
        zIndex: 40,
      }}
      className={cn(
        "flex flex-col items-center gap-1 rounded-lg border border-border bg-popover p-1.5 shadow-lg",
        // Never printed and never rasterised into an export: this is chrome,
        // not paper. Matches the existing `.float-image-hide-in-pdf` rule.
        "print:hidden float-image-hide-in-pdf",
      )}
    >
      <MenuButton
        icon={ImagePlus}
        label="Generate image"
        onClick={target.onGenerateImage}
        busy={target.generatingImage}
      />
      {/* Two swaps, because they answer two different complaints. "Another
          one of these" is one click and needs no dialog — it is the common
          case, and putting it behind a picker would tax it for no gain.
          "Not this KIND of question" changes the slot itself, which changes
          what the paper is worth, so it asks first. */}
      {target.canReplace ? (
        <>
          <MenuButton
            icon={RefreshCw}
            label="Swap for another question"
            onClick={target.onReplace}
            busy={target.replacing}
          />
          <MenuButton
            icon={Replace}
            label="Change question type"
            onClick={target.onChangeType}
          />
        </>
      ) : null}
      <div className="my-0.5 h-px w-full bg-border" />
      <MenuButton
        icon={Trash}
        label="Delete"
        onClick={target.onDelete}
        tone="destructive"
      />
    </div>,
    document.body,
  );
}
