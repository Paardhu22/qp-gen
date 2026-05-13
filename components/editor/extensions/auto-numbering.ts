import { Extension } from '@tiptap/core';

export const AutoNumbering = Extension.create({
  name: 'autoNumbering',

  onTransaction({ transaction }) {
    if (!transaction.docChanged) return;

    const { doc } = transaction;
    let questionCount = 0;

    // We use a separate set of changes to avoid infinite loops
    // But Tiptap's onTransaction is for side effects.
    // To actually modify the document, we should use a plugin or handle it in onUpdate.
  },

  addStorage() {
    return {
      count: 0,
    };
  },
});

// A better way to handle auto-numbering in Tiptap without infinite loops
// is to use a decorator or just update the attributes during a specific command.
// For simplicity and stability, I'll implement a function that the editor can call.

export function updateQuestionNumbers(editor: any) {
  if (!editor) return;

  let currentNumber = 1;
  const transactions = editor.state.tr;

  editor.state.doc.descendants((node: any, pos: number) => {
    if (node.type.name === 'questionItem') {
      if (node.attrs.number !== currentNumber) {
        transactions.setNodeMarkup(pos, undefined, {
          ...node.attrs,
          number: currentNumber,
        });
      }
      currentNumber++;
    }
  });

  if (transactions.docChanged) {
    editor.view.dispatch(transactions);
  }
}
