"use client";

/**
 * A browser harness for the pagination engine.
 *
 * The engine is pure layout: every decision it makes comes from
 * `getBoundingClientRect`, so none of it can be exercised by
 * `scripts/test-pagination-fit.mjs` (which covers only the arithmetic in
 * pagination-fit.ts) or by jsdom, which has no layout at all. That gap is why
 * two separate measurement bugs shipped — the engine was reading
 * `.doc-page-content`'s single node-view wrapper as if it were the page's
 * block list, and nothing anywhere could have caught it.
 *
 * This route mounts the real page/question/figure node views with the real
 * stylesheet and a canned document, and exposes the measurements on
 * `window.__paginationHarness` so a headless browser can assert on them. It
 * lives outside `app/(dashboard)/` deliberately: that group's client-side auth
 * guard would bounce it to /login and there would be nothing to measure.
 */

import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useEffect } from "react";

import { PaginatedDocument } from "@/components/editor/extensions/document-node";
import { PageNode } from "@/components/editor/extensions/page-node";
import {
  QuestionBlock,
  SectionBlock,
  InstructionBlock,
  PageBreak,
} from "@/components/editor/extensions/nodes";
import { FloatImage } from "@/components/editor/extensions/float-image";
import { MathBlock, InlineMath } from "@/components/editor/extensions/math-nodes";
import { PaginationEngine } from "@/components/editor/extensions/pagination-engine";

/** A real 600x400 PNG, inlined so the load is genuine but needs no backend. */
const FIGURE =
  "data:image/png;base64," +
  "iVBORw0KGgoAAAANSUhEUgAAAlgAAAGQCAIAAAD9V4nPAAAFM0lEQVR42u3VMREAMAwDsSAJf1qd" +
  "O3cPjsbyCYGXrzYzMwteucDMzITQzMxMCM3MzITQzMxMCM3MzIJDeO4DgJWEEAAhFEIAhFAIARBC" +
  "IQRACIUQACEUQgCEUAgBEEIhBEAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAI" +
  "AUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAI" +
  "AUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIAUAIARBCIQRACIUQACEUQgCEUAgBEEIh" +
  "BEAIhRAAIRRCAITQTQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAI" +
  "IQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAI" +
  "IQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQAIIQBCKIQACKEQAiCEQgiAEAohAEIohAAIoRAC" +
  "IIRCCIAQegoAIQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQA" +
  "IQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQAIQQA" +
  "IQQAIQQAIQQAIQQAIQQAIQQAIQQAIQRACIUQACEUQgCEUAgBEEIhBEAIhRAAIRRCAIRQCAEQQiEE" +
  "QAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgB" +
  "QAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgBQAgB" +
  "QAgBQAgBQAgBQAgBQAgBQAgBEEIhBEAIhRAAIRRCAIRQCAEQQiEEQAiFEAAhFEIAhNBTAAghAAgh" +
  "AAghAAghAAghAAghAAghAAghAAghAAghAAghAAghAAghAAghAAghAAghAAghAAghAAghAAghAAgh" +
  "AAghAAghAAghAAghAAghAAghAAghAAghAAghAAghAAghAAghAAghAAghAAghAAghAAghAAghAAgh" +
  "AAghAAghAAghAAghAEIohAAIoRACIIRCCIAQCiEAQiiEAAihEAIghEIIgBACgBACgBACgBACgBAC" +
  "gBACgBACgBACgBACgBACgBACgBACgBACgBACgBACgBACgBACgBACgBACgBACgBACgBACgBACgBAC" +
  "gBACgBACgBACgBACgBACgBACgBACgBACgBACgBACgBACgBACgBACgBACgBACgBACgBACgBACgBAC" +
  "gBACIIRCCIAQCiEAQiiEAAihEAIghEIIgBAKIQBCKIQACKGbABBCABBCABBCABBCABBCABBCABBC" +
  "ABBCABBCABBCABBCABBCABBCABBCABBCABBCABBCABBCABBCABBCABBCABBCABBCABBCABBCABBC" +
  "ABBCABBCABBCABBCABBCABBCABBCABBCABBCABBCABBCABBCABBCABBCABBCABBCABBCABBCAIRQ" +
  "CAEQQiEEQAiFEAAhFEIAhFAIARBCIQRACIUQACH0FABCCABCCABCCABCCABCCABCCABCCABCCABC" +
  "CABCCABCCABCCABCCABCCABCCABCCABCCAB/hNDMzCxnQmhmZkJoZmYmhGZmZkJoZmYmhGZmZjEb" +
  "RckYGvQI6BEAAAAASUVORK5CYII=";

const para = (text: string) => ({
  type: "paragraph",
  content: text ? [{ type: "text", text }] : [],
});

const question = (n: number, text: string, extra: any[] = []) => ({
  type: "questionBlock",
  attrs: { number: n, marks: 1, questionType: "MCQ" },
  content: [para(text), ...extra],
});

const STEMS = [
  "Why do sexually reproducing organisms generally show greater diversity than asexually reproducing ones?",
  "Which of the following statements about autotrophic nutrition is correct?",
  "Which of the following groups contains only biodegradable items?",
  "State the function of the diaphragm during inhalation and explain the pressure change involved.",
  "A concave mirror produces a three-times magnified real image. Where is the object placed?",
  "Explain why the sky appears blue while the setting sun appears red.",
  "Name the process by which plants lose water vapour, and state one factor affecting its rate.",
  "Distinguish between a homologous series and a functional group with one example of each.",
  "Why is the nucleus of an atom positively charged? Give a reason for your answer.",
  "Describe one method of preventing the rusting of iron and explain why it works.",
  "What is the role of decomposers in an ecosystem? Give two examples.",
  "Explain the difference between velocity and speed using a suitable example.",
];

/**
 * The reported shape: a full-width figure makes Q1 tall enough to push the
 * following questions over, and the paper runs past one page. Everything is
 * put on a single page here on purpose — the engine must do all the splitting
 * itself, which is also what happens when a stored paper is re-opened.
 */
const DOC = {
  type: "doc",
  content: [
    {
      type: "page",
      attrs: { pageId: "harness-1" },
      content: [
        {
          type: "sectionBlock",
          attrs: { title: "SECTION A" },
          content: [{ type: "text", text: "SECTION A" }],
        },
        {
          type: "instructionBlock",
          attrs: { variant: "general" },
          content: [para("All questions are compulsory.")],
        },
        question(1, "What does a switch do in an electric circuit?", [
          {
            type: "floatImage",
            attrs: { src: FIGURE, alt: "circuit", width: 660, align: "center" },
          },
        ]),
        ...STEMS.map((s, i) => question(i + 2, s)),
      ],
    },
  ],
};

export default function PaginationHarness() {
  const editor = useEditor(
    {
      immediatelyRender: false,
      extensions: [
        StarterKit.configure({ document: false }),
        PaginatedDocument,
        PageNode,
        SectionBlock,
        InstructionBlock,
        QuestionBlock,
        PageBreak,
        FloatImage,
        MathBlock,
        InlineMath,
        PaginationEngine,
      ],
      content: DOC,
      editorProps: {
        attributes: { class: "document-editor focus:outline-none text-black" },
      },
    },
    [],
  );

  useEffect(() => {
    if (!editor) return;

    (window as any).__paginationHarness = {
      /** How many blocks ProseMirror thinks each page holds. */
      nodeCounts: () => {
        const counts: number[] = [];
        editor.state.doc.descendants((node: any) => {
          if (node.type?.name === "page") counts.push(node.childCount);
        });
        return counts;
      },

      /**
       * What `Array.from(contentEl.children)` actually yields — the check that
       * decides whether the old engine's block indexing was ever valid.
       */
      domChildTags: () =>
        Array.from(document.querySelectorAll('[data-page-content="true"]')).map(
          (el) =>
            Array.from(el.children).map(
              (c) =>
                `${c.tagName.toLowerCase()}${
                  c.hasAttribute("data-node-view-content")
                    ? "[data-node-view-content]"
                    : `.${c.className}`
                }`,
            ),
        ),

      /**
       * Per page: unused px below the last block, and whether anything spills
       * past the content box. `overflow` must stay false — a page that clips
       * its own content is the failure the split rule exists to prevent.
       */
      pageFit: () =>
        Array.from(document.querySelectorAll('[data-page-content="true"]')).map(
          (el) => {
            const style = getComputedStyle(el as HTMLElement);
            const padBottom = parseFloat(style.paddingBottom) || 0;
            const limit = el.getBoundingClientRect().bottom - padBottom;
            const blocks = Array.from(
              (el as HTMLElement).querySelectorAll(
                ":scope > [data-node-view-content] > * > *",
              ),
            );
            if (blocks.length === 0) return { blocks: 0, free: null, overflow: false };
            const last = blocks[blocks.length - 1].getBoundingClientRect().bottom;
            return {
              blocks: blocks.length,
              free: Math.round(limit - last),
              overflow: blocks.some(
                (b) => b.getBoundingClientRect().bottom > limit + 1,
              ),
            };
          },
        ),

      /** Question numbers as rendered, page by page. */
      questionOrderByPage: () =>
        Array.from(document.querySelectorAll('[data-page-content="true"]')).map(
          (el) =>
            Array.from(el.querySelectorAll(".question-no")).map((n) =>
              (n.textContent || "").trim(),
            ),
        ),

      /** Is the figure actually rendered (not deleted by the onError path)? */
      figure: () => {
        const img = document.querySelector(
          ".float-image-img",
        ) as HTMLImageElement | null;
        if (!img) return null;
        const r = img.getBoundingClientRect();
        return {
          complete: img.complete,
          naturalWidth: img.naturalWidth,
          width: Math.round(r.width),
          height: Math.round(r.height),
        };
      },

      /**
       * What the OLD code measured for the pull-up decision, alongside what it
       * should have measured. `oldRunHeight` reads `contentEl.children` — one
       * wrapper — so it returns the height of the ENTIRE next page; the engine
       * compared that against the space left on the previous page and refused.
       */
      pullUpArithmetic: () => {
        const pages = Array.from(
          document.querySelectorAll('[data-page-content="true"]'),
        ) as HTMLElement[];
        if (pages.length < 2) return null;
        const next = pages[1];
        const blocks = Array.from(
          next.querySelectorAll(":scope > [data-node-view-content] > * > *"),
        );
        const wrapper = next.children[0];
        return {
          oldRunHeight: Math.round(wrapper.getBoundingClientRect().height),
          newRunHeight: blocks.length
            ? Math.round(blocks[0].getBoundingClientRect().height)
            : 0,
        };
      },

      /** Click the ½ preset, i.e. the exact interaction that was reported. */
      shrinkFigure: () => {
        const btn = Array.from(
          document.querySelectorAll(".float-img-btn"),
        ).find((b) => (b.textContent || "").trim() === "½") as HTMLElement | undefined;
        if (!btn) return false;
        btn.dispatchEvent(
          new MouseEvent("mousedown", { bubbles: true, cancelable: true }),
        );
        return true;
      },
    };

    (window as any).__harnessReady = true;
  }, [editor]);

  return (
    <div style={{ background: "#f1f5f9", padding: 24 }}>
      <EditorContent editor={editor} />
    </div>
  );
}
