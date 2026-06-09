import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";

// Issue 4 — OR invariant for `questionGroupBlock`.
//
// **Root cause** of the dropped-OR bug:
// The OR separator used to live as a regular sibling `paragraph` node
// between two `questionBlock` children. Dragging a child within the
// group can land it across that paragraph, the paragraph can be merged
// into adjacent content, or a copy/paste round-trip can drop it
// entirely. None of those operations are part of the user's intent,
// but each one silently destroys the OR relationship.
//
// **Fix**: take OR out of the document model entirely.
//   • Toolbar inserters emit groups with NO OR paragraph children
//     (toolbar.tsx — Issue 2 edits already do this).
//   • The CSS rule `[data-type="question-group"] >
//     [data-type="question-block"] + [data-type="question-block"]::before`
//     injects the OR label between every pair of consecutive question
//     siblings — purely visual, can never be dragged away.
//   • This plugin migrates legacy saved papers on first edit by
//     stripping any paragraph child of a `questionGroupBlock` whose
//     trimmed text is exactly "OR" (case-insensitive). After migration,
//     the CSS rule takes over visually, so the rendered output stays
//     identical for end-users.
//
// Because the plugin only RUNS when it finds an OR-text paragraph
// inside a question group, it is a no-op for newly created papers and
// it cannot loop on its own output (a re-scan after the deletion finds
// nothing left to delete).

const OR_TEXT_RE = /^or$/i;

export const OrGroupInvariant = Extension.create({
  name: "orGroupInvariant",

  addProseMirrorPlugins() {
    return [
      new Plugin({
        key: new PluginKey("orGroupInvariant"),
        appendTransaction: (transactions, _oldState, newState) => {
          if (!transactions.some((tr) => tr.docChanged)) return null;

          const removals: { from: number; to: number }[] = [];

          newState.doc.descendants((node, pos) => {
            if (node.type.name !== "questionGroupBlock") return;

            let childOffset = pos + 1;
            node.forEach((child) => {
              const size = child.nodeSize;
              if (
                child.type.name === "paragraph" &&
                OR_TEXT_RE.test(child.textContent.trim())
              ) {
                removals.push({ from: childOffset, to: childOffset + size });
              }
              childOffset += size;
            });
          });

          if (removals.length === 0) return null;

          const tr = newState.tr;
          // Apply right-to-left so earlier positions stay valid.
          for (let i = removals.length - 1; i >= 0; i--) {
            tr.delete(removals[i].from, removals[i].to);
          }
          tr.setMeta("addToHistory", false);
          return tr;
        },
      }),
    ];
  },
});
