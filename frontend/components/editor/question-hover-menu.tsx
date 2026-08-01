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
import { ImagePlus, Loader2, RefreshCw, Trash } from "lucide-react";

import { cn } from "@/lib/utils";

export interface QuestionMenuTarget {
  /** The DOM node of the question block the menu is anchored to. */
  element: HTMLElement;
  /** Question text, used as the subject for image generation. */
  text: string;
  /** Only generated questions have a blueprint slot to regenerate against. */
  canReplace: boolean;
  onReplace: () => void;
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

function useAnchorRect(element: HTMLElement | null) {
  const [rect, setRect] = React.useState<DOMRect | null>(null);

  React.useEffect(() => {
    if (!element) {
      setRect(null);
      return;
    }
    const measure = () => setRect(element.getBoundingClientRect());
    measure();

    // The editor scrolls inside its own container and the page can resize, so
    // a position measured once drifts. Observing both keeps the menu attached
    // to the question rather than to where the question used to be.
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    window.addEventListener("scroll", measure, true);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("scroll", measure, true);
      window.removeEventListener("resize", measure);
    };
  }, [element]);

  return rect;
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
        "flex h-7 items-center gap-1.5 rounded-md px-2 text-[11px] font-medium transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-60",
        tone === "destructive"
          ? "text-destructive hover:bg-destructive/10"
          : "text-foreground hover:bg-muted",
      )}
    >
      {busy ? (
        <Loader2 className="size-4 animate-spin" />
      ) : (
        <Icon className="size-4" />
      )}
    </button>
  );
}

export function QuestionHoverMenu({ target, onMenuEnter, onMenuLeave }: Props) {
  const rect = useAnchorRect(target?.element ?? null);
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => setMounted(true), []);

  if (!mounted || !target || !rect) return null;

  const MENU_WIDTH = 40; // Approximate width for icon-only or vertical layout
  const top = rect.top + (rect.height / 2) - 50; // Roughly center vertically (menu is taller now)
  // Float inside the right edge to avoid a hover gap
  const left = rect.right - MENU_WIDTH - 8;

  return createPortal(
    <div
      role="toolbar"
      aria-label="Question actions"
      data-question-menu="true"
      onMouseEnter={onMenuEnter}
      onMouseLeave={onMenuLeave}
      style={{
        position: "fixed",
        top,
        left,
        zIndex: 60,
      }}
      className={cn(
        "flex flex-col items-center gap-1 rounded-lg border border-border bg-popover p-1.5 shadow-lg",
        "animate-in fade-in-0 zoom-in-95 duration-100",
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
      {target.canReplace ? (
        <MenuButton
          icon={RefreshCw}
          label="Swap"
          onClick={target.onReplace}
          busy={target.replacing}
        />
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
