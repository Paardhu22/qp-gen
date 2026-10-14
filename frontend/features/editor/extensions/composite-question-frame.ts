import { Extension } from "@tiptap/core";
import type { Node as ProseMirrorNode } from "@tiptap/pm/model";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";
import { groupQuestionRuns } from "../question-nodes";

type Entry = { node: ProseMirrorNode; pos: number; page: number };
const key = new PluginKey<DecorationSet>("compositeQuestionFrame");

function frames(doc: ProseMirrorNode): DecorationSet {
  const decorations: Decoration[] = [];
  const decorate = (entries: Entry[]) => {
    for (const { head, body } of groupQuestionRuns(entries, ({ node }) => ({
      type: node.type.name, questionType: node.attrs.questionType,
    }))) {
      if (!body.length) continue;
      decorations.push(Decoration.node(head.pos, head.pos + head.node.nodeSize, {
        class: `composite-question-head${body[0].page !== head.page ? " composite-fragment-end" : ""}`,
      }));
      body.forEach((entry, index) => {
        // Close/reopen the frame at page edges without adding wrapper nodes:
        // each paragraph remains a legal pagination seam and stays editable.
        const first = (index === 0 ? head : body[index - 1]).page !== entry.page;
        const last = index === body.length - 1 || body[index + 1].page !== entry.page;
        decorations.push(Decoration.node(entry.pos, entry.pos + entry.node.nodeSize, {
          class: `composite-question-body${first ? " composite-fragment-start" : ""}${last ? " composite-fragment-end" : ""}`,
        }));
      });
    }
  };
  const entries: Entry[] = [];
  doc.forEach((page, pagePos) => {
    page.forEach((node, offset) => {
      const pos = pagePos + 1 + offset;
      entries.push({ node, pos, page: pagePos });
      if (node.type.name === "questionGroupBlock") {
        const branches: Entry[] = [];
        node.forEach((branch, branchOffset) => {
          branches.push({ node: branch, pos: pos + 1 + branchOffset, page: pagePos });
        });
        decorate(branches);
      }
    });
  });
  decorate(entries);
  return DecorationSet.create(doc, decorations);
}

/** Presentation only: no document migration and no work on scroll/selection. */
export const CompositeQuestionFrame = Extension.create({
  name: "compositeQuestionFrame",
  addProseMirrorPlugins() {
    return [new Plugin({
      key,
      state: {
        init: (_, state) => frames(state.doc),
        apply: (tr, previous) => tr.docChanged ? frames(tr.doc) : previous,
      },
      props: { decorations: (state) => key.getState(state) },
    })];
  },
});
