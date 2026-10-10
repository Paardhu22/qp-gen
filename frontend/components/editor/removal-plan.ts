/**
 * Which ranges to delete when the review tray pulls questions back out.
 *
 * A question is matched by its section title plus the first 60 characters of
 * its text — enough to tell questions in one section apart without breaking
 * on whitespace. A section header the removal leaves with no questions goes
 * too, so undoing a whole inserted section leaves no bare "SECTION B" behind.
 *
 * ## Composite questions are runs, not blocks
 *
 * A passage, grammar set or extract is inserted as a head `questionBlock`
 * holding only its preamble ("Extract:") followed by sibling paragraphs —
 * see `buildQuestionBlocks`. Matching the head's text alone failed, because
 * the preamble is shorter than the 60 characters compared, so Undo did
 * nothing; and deleting the head alone would have left the passage behind.
 * So a head is matched by its whole run, and the run goes with it.
 *
 * The run is the siblings after the head whose text is part of the question
 * the tray holds, continuing onto the next page when pagination split it.
 * Reading it off the tray's own text, rather than "every paragraph until the
 * next question", means a paragraph the teacher typed under a question is
 * never taken with it.
 *
 * Pure and import-free, so `scripts/test-removal-plan.mjs` can compile and
 * run it without an editor.
 */

export interface RemovalTarget {
  sectionTitle: string;
  content: string;
}

export interface Range {
  from: number;
  to: number;
}

/** Blocks that end a run. Mirrors STRUCTURAL_BLOCKS in question-nodes.ts. */
const STRUCTURAL = new Set([
  "questionBlock",
  "groupedQuestionBlock",
  "questionGroupBlock",
  "sectionBlock",
  "instructionBlock",
  "paperHeaderBlock",
  "pageBreak",
]);

const squash = (s: string) => s.replace(/\s+/g, " ").trim();
const normalize = (s: string) => squash(s).slice(0, 120);

interface Entry {
  node: any;
  pos: number;
  parent: any;
}

/** Ranges in the order found; delete them bottom-up. */
export function planRemovals(doc: any, requests: RemovalTarget[]): Range[] {
  const targets = requests.map((r) => ({
    sectionTitle: normalize(r.sectionTitle),
    content: normalize(r.content),
    full: squash(r.content),
  }));

  const entries: Entry[] = [];
  doc.descendants((node: any, pos: number, parent: any) => {
    entries.push({ node, pos, parent });
  });

  /** The next block after `i` at the same level, crossing onto the next page. */
  const nextSibling = (i: number): number => {
    const parent = entries[i].parent;
    const onPage = parent?.type?.name === "page";
    for (let j = i + 1; j < entries.length; j += 1) {
      const other = entries[j].parent;
      if (other === parent) return j;
      if (onPage && other?.type?.name === "page" && other !== parent) return j;
    }
    return -1;
  };

  /** The head's run: the following siblings whose text is in `full`. */
  const runOf = (head: number, full: string): number[] => {
    const run: number[] = [];
    let pending: number[] = [];
    for (let k = nextSibling(head); k !== -1; k = nextSibling(k)) {
      const node = entries[k].node;
      if (STRUCTURAL.has(node.type?.name)) break;
      const text = squash(String(node.textContent || ""));
      if (!text) {
        pending.push(k); // a blank line inside the run, kept only if it continues
      } else if (full.includes(text)) {
        run.push(...pending, k);
        pending = [];
      } else {
        break;
      }
    }
    return run;
  };

  const ranges: Range[] = [];
  let currentSectionTitle = "";
  let section: (Range & { removed: number; kept: number }) | null = null;
  const dropIfEmptied = () => {
    if (section && section.removed > 0 && section.kept === 0) {
      ranges.push({ from: section.from, to: section.to });
    }
  };

  entries.forEach(({ node, pos }, index) => {
    if (node.type.name === "sectionBlock") {
      dropIfEmptied();
      section = { from: pos, to: pos + node.nodeSize, removed: 0, kept: 0 };
      currentSectionTitle = normalize(String(node.textContent || ""));
      return;
    }
    if (node.type.name !== "questionBlock" && node.type.name !== "groupedQuestionBlock") {
      return;
    }
    const nodeText = normalize(String(node.textContent || ""));
    let run: number[] = [];
    const hit = targets.some((t) => {
      if (t.sectionTitle !== "" && t.sectionTitle !== currentSectionTitle) return false;
      const prefix = t.content.slice(0, 60);
      const candidate = runOf(index, t.full);
      const runText = normalize(
        [node, ...candidate.map((k) => entries[k].node)]
          .map((n) => String(n.textContent || ""))
          .join(" "),
      );
      if (nodeText.startsWith(prefix) || (candidate.length > 0 && runText.startsWith(prefix))) {
        run = candidate;
        return true;
      }
      return false;
    });
    if (hit) {
      ranges.push({ from: pos, to: pos + node.nodeSize });
      for (const k of run) {
        ranges.push({ from: entries[k].pos, to: entries[k].pos + entries[k].node.nodeSize });
      }
      if (section) section.removed += 1;
    } else if (section) {
      section.kept += 1;
    }
  });
  dropIfEmptied();

  return ranges;
}
