/**
 * Document-derived bookkeeping the editor re-runs after every change: question
 * numbers (and OR-branch labels), and each section's "N x M = T Marks" summary
 * and instruction line.
 *
 * These are computed from the document, not authored by the user, so their
 * transactions are kept out of the undo history (`markDerived`). Were they
 * recorded, every added or deleted question would be followed by a hidden
 * "renumber" step and Ctrl+Z would revert that instead of the user's action.
 */

import { markDerived } from "./history";

// ==================================
// Auto-numbering utility
// ==================================
export function updateQuestionNumbers(editor: any) {
  if (!editor) return;
  let currentNumber = 1;
  const tr = editor.state.tr;
  const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

  editor.state.doc.descendants((node: any, pos: number) => {
    // OR group occupies ONE question slot. Assign its number, then
    // walk its branches and stamp each with `subLabel = "<n>(A)"` /
    // "<n>(B)" so the QuestionBlock NodeView renders the OR-branch
    // format ("31(A)") instead of its standalone number. Anything
    // outside an OR group keeps subLabel === null.
    if (node.type.name === "questionGroupBlock") {
      const groupNumber = currentNumber;
      if (node.attrs.number !== groupNumber) {
        tr.setNodeMarkup(pos, undefined, { ...node.attrs, number: groupNumber });
      }
      let branchIndex = 0;
      let childOffset = pos + 1;
      node.forEach((child: any) => {
        if (
          child.type.name === "questionBlock" ||
          child.type.name === "groupedQuestionBlock"
        ) {
          const letter = letters[branchIndex] || `${branchIndex + 1}`;
          const desired = `${groupNumber}(${letter})`;
          if (child.attrs.subLabel !== desired) {
            tr.setNodeMarkup(childOffset, undefined, {
              ...child.attrs,
              subLabel: desired,
            });
          }
          branchIndex += 1;
        }
        childOffset += child.nodeSize;
      });
      currentNumber++;
      return false; // OR group is counted once; skip recursion.
    }

    if (
      node.type.name === "questionBlock" ||
      node.type.name === "groupedQuestionBlock"
    ) {
      const updates: Record<string, unknown> = {};
      if (node.attrs.number !== currentNumber) {
        updates.number = currentNumber;
      }
      // Drag-out from an OR group must drop the stale subLabel,
      // otherwise the standalone question keeps showing "31(A)".
      if (node.attrs.subLabel !== null) {
        updates.subLabel = null;
      }
      if (Object.keys(updates).length > 0) {
        tr.setNodeMarkup(pos, undefined, { ...node.attrs, ...updates });
      }
      currentNumber++;
    }
  });

  if (tr.docChanged) {
    editor.view.dispatch(markDerived(tr));
  }
}

type SectionSummary = {
  pos: number;
  title: string;
  questionCount: number;
  totalMarks: number;
  marksEach: number | null;
};

function buildSectionSummaryText(section: SectionSummary) {
  if (section.questionCount === 0) return "";
  if (section.marksEach !== null) {
    return `${section.questionCount} x ${section.marksEach} = ${section.totalMarks} Marks`;
  }
  return `${section.questionCount} Questions = ${section.totalMarks} Marks`;
}

function buildInstructionLine(section: SectionSummary) {
  if (section.questionCount === 0) {
    return `${section.title} has no questions.`;
  }
  if (section.marksEach !== null) {
    const markLabel = section.marksEach === 1 ? "mark" : "marks";
    return `${section.title} has ${section.questionCount} questions carrying ${section.marksEach} ${markLabel} each.`;
  }
  return `${section.title} has ${section.questionCount} questions carrying a total of ${section.totalMarks} marks.`;
}

export function updateSectionSummaries(editor: any) {
  if (!editor) return;

  const { doc } = editor.state;
  const tr = editor.state.tr;
  const sections: SectionSummary[] = [];
  let currentSection: SectionSummary | null = null;
  let currentMarks: Set<number> = new Set();

  doc.descendants((node: any, pos: number) => {
    if (node.type.name === "sectionBlock") {
      const sec = currentSection;
      if (sec) {
        const marksEach = currentMarks.size === 1 ? [...currentMarks][0] : null;
        sections.push({
          ...(sec as SectionSummary),
          marksEach,
        });
      }

      currentSection = {
        pos,
        title: (node.textContent || "Section").trim(),
        questionCount: 0,
        totalMarks: 0,
        marksEach: null,
      };
      currentMarks = new Set();
      return;
    }

    // OR group counts as ONE question slot; don't recurse into its children.
    if (node.type.name === "questionGroupBlock" && currentSection) {
      // Use the marks of the first question child (plain or grouped) as
      // representative — both branches carry equal marks by definition.
      let groupMarks = 0;
      node.forEach((child: any) => {
        if (
          groupMarks === 0 &&
          (child.type.name === "questionBlock" ||
            child.type.name === "groupedQuestionBlock")
        ) {
          groupMarks = Number(child.attrs?.marks ?? 0) || 0;
        }
      });
      currentSection.questionCount += 1;
      currentSection.totalMarks += groupMarks;
      if (groupMarks > 0) currentMarks.add(groupMarks);
      return false; // skip all children — OR group is ONE question slot
    }

    if (
      (node.type.name === "questionBlock" ||
        node.type.name === "groupedQuestionBlock") &&
      currentSection
    ) {
      const marks = Number(node.attrs?.marks ?? 0) || 0;
      currentSection.questionCount += 1;
      currentSection.totalMarks += marks;
      if (marks > 0) currentMarks.add(marks);
    }
  });

  const finalSec = currentSection;
  if (finalSec) {
    const marksEach = currentMarks.size === 1 ? [...currentMarks][0] : null;
    sections.push({
      ...(finalSec as SectionSummary),
      marksEach,
    });
  }

  sections.forEach((section) => {
    const node = doc.nodeAt(section.pos);
    if (!node) return;

    const summaryText = buildSectionSummaryText(section);
    const nextAttrs = {
      ...node.attrs,
      questionCount: section.questionCount,
      totalMarks: section.totalMarks,
      marksEach: section.marksEach,
      summaryText,
    };

    const hasChanged =
      node.attrs.questionCount !== nextAttrs.questionCount ||
      node.attrs.totalMarks !== nextAttrs.totalMarks ||
      node.attrs.marksEach !== nextAttrs.marksEach ||
      node.attrs.summaryText !== nextAttrs.summaryText;

    if (hasChanged) {
      tr.setNodeMarkup(section.pos, undefined, nextAttrs);
    }
  });

  const instructionLines =
    sections.length > 0
      ? [
          `This question paper has ${sections.length} section${
            sections.length === 1 ? "" : "s"
          }.`,
          ...sections.map((section) => buildInstructionLine(section)),
        ]
      : [];

  doc.descendants((node: any, pos: number) => {
    if (node.type.name !== "instructionBlock") return;
    if (node.attrs?.variant !== "general") return;

    const currentItems = node.attrs?.summaryItems || [];
    const isSame =
      Array.isArray(currentItems) &&
      currentItems.length === instructionLines.length &&
      currentItems.every(
        (item: string, index: number) => item === instructionLines[index],
      );

    if (!isSame) {
      tr.setNodeMarkup(pos, undefined, {
        ...node.attrs,
        summaryItems: instructionLines,
      });
    }
  });

  if (tr.docChanged) {
    editor.view.dispatch(markDerived(tr));
  }
}
