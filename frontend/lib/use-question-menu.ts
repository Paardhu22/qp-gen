"use client";

/**
 * Drives the floating question menu from the editor, by DOM delegation.
 *
 * The alternative was passing callbacks into every NodeView, which means every
 * question block re-renders when any menu state changes and the editor's React
 * tree has to reach inside ProseMirror's. Delegation keeps NodeViews dumb: a
 * question block advertises `data-question-block` and `data-can-replace`, and
 * everything else is resolved here from a DOM node via `posAtDOM`.
 *
 * ## The close delay is not a nicety
 *
 * The menu floats ABOVE the block it belongs to, so the pointer necessarily
 * leaves the block to reach it. Closing on `mouseleave` would shut the menu on
 * the way to clicking it — the classic hover-menu bug. The close is deferred
 * and cancelled by entering either the block or the menu.
 */

import * as React from "react";
import { toast } from "sonner";

import {
  generateQuestionImage,
  fetchQuestionImageStyles,
  type QuestionImageStyle,
  type QuestionImageStyleOption,
} from "@/lib/api-client";
import { replaceQuestionNode } from "@/components/editor/extensions/nodes";
import { SIZE_HALF } from "@/components/editor/extensions/float-image";

/** Long enough to cross the gap to the menu, short enough not to feel stuck. */
const CLOSE_DELAY_MS = 500;

/**
 * The child types that hold a question's *answers* rather than its stem.
 *
 * Both `questionBlock` and `groupedQuestionBlock` are
 * `(paragraph | bulletList | orderedList | mathBlock | floatImage)+`, and in
 * both the same shape holds: the stem comes first as paragraphs (and the odd
 * `mathBlock`), then a single list carries the MCQ options or the case-study
 * sub-questions.
 */
const ANSWER_LISTS = new Set(["bulletList", "orderedList"]);

/**
 * Where a generated figure belongs inside a question: after the stem, before
 * the options.
 *
 * Appending at the end of the node put the picture underneath the options of an
 * MCQ and underneath every sub-question of a case-study block — so the figure
 * the question depends on appeared after the choices that depend on it, which
 * on a printed paper reads as belonging to whatever comes next.
 *
 * Returning the position of the first answer list puts the figure directly
 * below the stem. A question with no list at all (SHORT / LONG) has no options
 * to come before, so it keeps the old end-of-content position.
 */
function figureInsertPos(node: any, nodePos: number): number {
  // +1 steps past the question node's own opening token into its content.
  let offset = nodePos + 1;

  for (let i = 0; i < node.childCount; i += 1) {
    const child = node.child(i);
    if (ANSWER_LISTS.has(child.type?.name)) return offset;
    offset += child.nodeSize;
  }

  return nodePos + node.nodeSize - 1;
}

interface ActiveQuestion {
  element: HTMLElement;
  pos: number;
  text: string;
  canReplace: boolean;
}

export function useQuestionMenu(editor: any) {
  const [active, setActive] = React.useState<ActiveQuestion | null>(null);
  const [replacing, setReplacing] = React.useState(false);
  const [styleDialogOpen, setStyleDialogOpen] = React.useState(false);
  const [generatingImage, setGeneratingImage] = React.useState(false);
  const [styles, setStyles] = React.useState<QuestionImageStyleOption[]>([]);

  const closeTimer = React.useRef<number | null>(null);
  // The question the dialog is for, captured when it opens. Without this the
  // hover can move away mid-generation and the image lands on a different
  // question than the teacher pointed at.
  const pendingRef = React.useRef<ActiveQuestion | null>(null);

  const cancelClose = React.useCallback(() => {
    if (closeTimer.current !== null) {
      window.clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }, []);

  const scheduleClose = React.useCallback(() => {
    cancelClose();
    closeTimer.current = window.setTimeout(() => {
      setActive(null);
      closeTimer.current = null;
    }, CLOSE_DELAY_MS);
  }, [cancelClose]);

  const resolveFrom = React.useCallback(
    (element: HTMLElement): ActiveQuestion | null => {
      if (!editor || editor.isDestroyed || !editor.isEditable) return null;
      try {
        const pos = editor.view.posAtDOM(element, 0);
        if (typeof pos !== "number" || pos < 0) return null;
        const resolved = editor.state.doc.resolve(Math.min(pos, editor.state.doc.content.size));
        // Walk out to the question block itself: posAtDOM lands inside it.
        for (let depth = resolved.depth; depth > 0; depth -= 1) {
          const node = resolved.node(depth);
          if (
            node.type.name === "questionBlock" ||
            node.type.name === "groupedQuestionBlock"
          ) {
            return {
              element,
              pos: resolved.before(depth),
              text: node.textContent || "",
              canReplace: element.dataset.canReplace === "true",
            };
          }
        }
      } catch {
        // A DOM node ProseMirror no longer maps (mid-transaction). Ignore —
        // the next hover resolves cleanly.
      }
      return null;
    },
    [editor],
  );

  // ── Hover ──────────────────────────────────────────────────────────────
  React.useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    const root: HTMLElement | null = editor.view?.dom ?? null;
    if (!root) return;

    const onOver = (event: Event) => {
      const target = event.target as HTMLElement | null;
      const block = target?.closest?.(
        "[data-question-block='true']",
      ) as HTMLElement | null;
      if (!block) return;
      cancelClose();
      setActive((current) =>
        current?.element === block ? current : resolveFrom(block),
      );
    };

    const onOut = (event: Event) => {
      const related = (event as MouseEvent).relatedTarget as HTMLElement | null;
      // Moving within the same block is not leaving it.
      if (related?.closest?.("[data-question-block='true']")) return;
      scheduleClose();
    };

    root.addEventListener("mouseover", onOver);
    root.addEventListener("mouseout", onOut);
    return () => {
      root.removeEventListener("mouseover", onOver);
      root.removeEventListener("mouseout", onOut);
      cancelClose();
    };
  }, [editor, resolveFrom, cancelClose, scheduleClose]);

  // ── Caret ──────────────────────────────────────────────────────────────
  // Hover is a mouse affordance. A keyboard or touch user reaches a question
  // by putting the caret in it, and must get the same actions.
  React.useEffect(() => {
    if (!editor || editor.isDestroyed) return;

    const sync = () => {
      if (!editor.isEditable) return;
      const { $from } = editor.state.selection;
      for (let depth = $from.depth; depth > 0; depth -= 1) {
        const node = $from.node(depth);
        if (
          node.type.name === "questionBlock" ||
          node.type.name === "groupedQuestionBlock"
        ) {
          const pos = $from.before(depth);
          const dom = editor.view.nodeDOM(pos) as HTMLElement | null;
          const element: HTMLElement | null =
            dom?.nodeType === 1
              ? ((dom as HTMLElement).closest(
                  "[data-question-block='true']",
                ) as HTMLElement | null) ?? (dom as HTMLElement)
              : null;
          if (element) {
            cancelClose();
            setActive({
              element,
              pos,
              text: node.textContent || "",
              canReplace: element.dataset?.canReplace === "true",
            });
          }
          return;
        }
      }
    };

    editor.on("selectionUpdate", sync);
    return () => {
      editor.off("selectionUpdate", sync);
    };
  }, [editor, cancelClose]);

  // Style list is small and stable — fetched once, lazily, on first need.
  const ensureStyles = React.useCallback(async () => {
    if (styles.length > 0) return styles;
    try {
      const fetched = await fetchQuestionImageStyles();
      setStyles(fetched);
      return fetched;
    } catch (error) {
      console.error("Could not load image styles:", error);
      // A hard-coded fallback keeps the feature usable when the endpoint is
      // unreachable; the server list is authoritative when it answers.
      const fallback: QuestionImageStyleOption[] = [
        { value: "line_art", label: "Line art", description: "Clean black-and-white textbook figure." },
        { value: "realistic", label: "Realistic", description: "Photographic depiction." },
        { value: "cartoon", label: "Cartoon", description: "Friendly illustration." },
      ];
      setStyles(fallback);
      return fallback;
    }
  }, [styles]);

  const openImageDialog = React.useCallback(() => {
    if (!active) return;
    pendingRef.current = active;
    void ensureStyles();
    setStyleDialogOpen(true);
  }, [active, ensureStyles]);

  const handleDelete = React.useCallback(() => {
    const target = active;
    if (!editor || !target) return;
    const node = editor.state.doc.nodeAt(target.pos);
    if (!node) return;
    editor
      .chain()
      .focus()
      .deleteRange({ from: target.pos, to: target.pos + node.nodeSize })
      .run();
    setActive(null);
  }, [editor, active]);

  const handleReplace = React.useCallback(() => {
    const target = active;
    if (!editor || !target) return;
    const node = editor.state.doc.nodeAt(target.pos);
    if (!node) return;
    void replaceQuestionNode({
      editor,
      getPos: () => target.pos,
      node,
      onBusy: setReplacing,
    });
  }, [editor, active]);

  const handleGenerateImage = React.useCallback(
    async (style: QuestionImageStyle) => {
      const target = pendingRef.current;
      if (!editor || !target) return;

      setGeneratingImage(true);
      try {
        const { imageUrl, cached } = await generateQuestionImage({
          questionText: target.text,
          style,
        });

        const node = editor.state.doc.nodeAt(target.pos);
        if (!node) {
          toast.error("That question is no longer in the paper.");
          return;
        }

        // Inside the question's own content (never after the whole block, which
        // would orphan the figure when questions reorder) and above the options
        // it illustrates. See `figureInsertPos`.
        editor
          .chain()
          .focus()
          .insertContentAt(figureInsertPos(node, target.pos), {
            type: "floatImage",
            attrs: {
              src: imageUrl,
              alt: "",
              width: SIZE_HALF,
              align: "center",
            },
          })
          .run();

        setStyleDialogOpen(false);
        toast.success(
          cached
            ? "Added a picture you had already generated for this question."
            : "Picture added — check it before using the paper.",
        );
      } catch (error: any) {
        toast.error(
          error?.message || "The image could not be generated. Try again.",
        );
      } finally {
        setGeneratingImage(false);
      }
    },
    [editor],
  );

  return {
    active,
    replacing,
    generatingImage,
    styles,
    styleDialogOpen,
    setStyleDialogOpen,
    openImageDialog,
    handleDelete,
    handleReplace,
    handleGenerateImage,
    onMenuEnter: cancelClose,
    onMenuLeave: scheduleClose,
  };
}
