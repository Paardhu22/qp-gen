"use client";

/**
 * A browser harness for the paper exports and the masthead.
 *
 * Both exports read the live editor: the PDF rasterises its node views and
 * the Word file is built from its document. Neither can be exercised without
 * a browser, and the masthead's logo layout depends on the logo's real shape.
 * This route mounts the real editor extensions on a canned paper, lets the
 * logo be swapped for each shape a school might upload, and exposes both
 * exporters on `window.__exportHarness` so a headless browser can fetch the
 * files. Like /pagination-harness, it lives outside `app/(dashboard)/` so the
 * auth guard does not bounce it.
 *
 *   /export-harness?logo=wide|square|tall|none&align=auto|left|right|top&readonly=1
 */

import { Suspense, useEffect, useMemo } from "react";
import { useSearchParams } from "next/navigation";
import { EditorContent, useEditor } from "@tiptap/react";

import { getTiptapExtensions } from "@/components/tiptap-editor";
import { buildQuestionBlocks } from "@/components/editor/question-nodes";

const svg = (width: number, height: number, body: string) =>
  "data:image/svg+xml;base64," +
  btoa(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">${body}</svg>`,
  );

/** One of each shape a school uploads: a wordmark, a crest, an emblem. */
const LOGOS: Record<string, string> = {
  wide: svg(
    420,
    110,
    `<circle cx="55" cy="55" r="44" fill="#d61f69"/><circle cx="85" cy="55" r="30" fill="#1d4ed8" opacity=".85"/>` +
      `<text x="135" y="52" font-family="Arial" font-weight="700" font-size="29" fill="#111">DECCAN SPRINGS</text>` +
      `<text x="137" y="88" font-family="Arial" font-size="24" fill="#444">GLOBAL SCHOOL</text>`,
  ),
  square: svg(
    200,
    200,
    `<path d="M100 8 L184 40 L172 136 Q100 196 100 196 Q28 136 28 136 L16 40 Z" fill="#1e3a8a"/>` +
      `<path d="M100 40 L150 60 L142 124 Q100 162 100 162 Q58 124 58 124 L50 60 Z" fill="#facc15"/>` +
      `<text x="100" y="118" text-anchor="middle" font-family="Georgia" font-weight="700" font-size="44" fill="#1e3a8a">GS</text>`,
  ),
  tall: svg(
    120,
    210,
    `<rect x="10" y="10" width="100" height="190" rx="50" fill="#065f46"/>` +
      `<circle cx="60" cy="70" r="32" fill="#fef3c7"/><rect x="40" y="120" width="40" height="60" fill="#fef3c7"/>`,
  ),
};

const para = (text: string, attrs: Record<string, unknown> = {}) => ({
  type: "paragraph",
  attrs,
  content: text ? [{ type: "text", text }] : [],
});

const heading = (level: number, text: string) => ({
  type: "heading",
  attrs: { level },
  content: [{ type: "text", text }],
});

const cell = (type: "tableHeader" | "tableCell", text: string) => ({
  type,
  content: [para(text)],
});

function header(logoUrl: string, logoAlign: string) {
  return {
    type: "paperHeaderBlock",
    attrs: { logoUrl, logoAlign, showDate: true, dateValue: "2026-10-04" },
    content: [
      heading(1, "Deccan Springs Global School"),
      heading(2, "Half-Yearly Examination 2026-27"),
      {
        type: "table",
        content: [
          {
            type: "tableRow",
            content: ["Subject", "Grade", "Set", "Max Marks", "Time"].map((t) =>
              cell("tableHeader", t),
            ),
          },
          {
            type: "tableRow",
            content: ["ICT", "X", "A", "50", "90 min"].map((t) => cell("tableCell", t)),
          },
        ],
      },
    ],
  };
}

/**
 * Number the questions as the editor does (`updateQuestionNumbers`), which
 * runs in the editor component this harness does not mount: an OR group is
 * one number, its branches "5(A)", "5(B)".
 */
function numbered(doc: any) {
  let next = 1;
  for (const block of doc.content[0].content) {
    if (block.type === "questionBlock") block.attrs.number = next++;
    if (block.type === "questionGroupBlock") {
      block.content.forEach((branch: any, i: number) => {
        branch.attrs.subLabel = `${next}(${String.fromCharCode(65 + i)})`;
      });
      next += 1;
    }
  }
  return doc;
}

function paper(logoUrl: string, logoAlign: string) {
  const mcq = (content: string, options: string[]) =>
    buildQuestionBlocks({ content, type: "MCQ", options, marks: 1 });
  return {
    type: "doc",
    content: [
      {
        type: "page",
        attrs: { pageId: "export-1" },
        content: [
          header(logoUrl, logoAlign),
          {
            type: "instructionBlock",
            attrs: {
              variant: "general",
              summaryItems: [
                "This question paper has 2 sections.",
                "SECTION A has 3 questions carrying 1 mark each.",
              ],
            },
            content: [para("All questions are compulsory.")],
          },
          {
            type: "sectionBlock",
            attrs: { summaryText: "3 x 1 = 3 Marks" },
            content: [{ type: "text", text: "SECTION A" }],
          },
          ...mcq("What is a key difference between a switch and a hub?", [
            "Switch sends data to all devices; hub sends only to the intended device",
            "Hub sends data to all devices; switch sends only to the intended device",
            "Both send data only to the intended device",
            "Neither forwards data",
          ]),
          ...mcq("Which shortcut key is used to undo the last action?", [
            "Ctrl + Y",
            "Ctrl + Z",
            "Ctrl + X",
            "Ctrl + U",
          ]),
          ...mcq("The value of \\(\\sqrt{49} + 2^3\\) is", ["9", "15", "13", "11"]),
          {
            type: "sectionBlock",
            attrs: { summaryText: "", summaryOverride: "Answer any 2" },
            content: [{ type: "text", text: "SECTION B" }],
          },
          ...buildQuestionBlocks({
            content: "Write the steps to insert a table with 4 rows and 3 columns in a Writer document.",
            type: "SHORT",
            marks: 3,
          }),
          {
            type: "questionGroupBlock",
            content: [
              ...buildQuestionBlocks({
                content: "Differentiate between RAM and ROM (any two points).",
                type: "SHORT",
                marks: 2,
              }),
              ...buildQuestionBlocks({
                content: "Explain why H₂O is called a universal solvent.",
                type: "SHORT",
                marks: 2,
              }),
            ],
          },
        ],
      },
    ],
  };
}

function ExportHarness() {
  const params = useSearchParams();
  const logo = params.get("logo") ?? "wide";
  const align = params.get("align") ?? "auto";
  const readonly = params.get("readonly") === "1";
  const content = useMemo(() => numbered(paper(LOGOS[logo] ?? "", align)), [logo, align]);

  const editor = useEditor(
    {
      immediatelyRender: false,
      editable: !readonly,
      extensions: getTiptapExtensions(!readonly),
      content,
      editorProps: {
        attributes: {
          id: "tiptap-paper-container",
          class: "document-editor focus:outline-none text-black",
        },
      },
    },
    [content, readonly],
  );

  useEffect(() => {
    if (!editor) return;
    const asBase64 = async (blob: Blob) => {
      const bytes = new Uint8Array(await blob.arrayBuffer());
      let binary = "";
      bytes.forEach((b) => (binary += String.fromCharCode(b)));
      return btoa(binary);
    };
    (window as any).__exportHarness = {
      json: () => editor.getJSON(),
      docx: async () => {
        const { exportToDocx } = await import("@/lib/export-docx");
        return asBase64(await exportToDocx(editor.view.dom as HTMLElement, "harness.docx"));
      },
      pdf: async () => {
        const { exportToPDF } = await import("@/lib/export-pdf");
        return asBase64(await exportToPDF("tiptap-paper-container", "harness.pdf"));
      },
    };
  }, [editor]);

  return <EditorContent editor={editor} />;
}

// `useSearchParams` needs a Suspense boundary to build.
export default function ExportHarnessPage() {
  return (
    <Suspense>
      <ExportHarness />
    </Suspense>
  );
}
