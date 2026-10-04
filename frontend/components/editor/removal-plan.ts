/**
 * Which ranges to delete when the review tray pulls questions back out.
 *
 * A question is matched by its section title plus the first 60 characters of
 * its text — enough to tell questions in one section apart without breaking
 * on whitespace. A section header the removal leaves with no questions goes
 * too, so undoing a whole inserted section leaves no bare "SECTION B" behind.
 *
 * Pure, so `scripts/test-removal-plan.mjs` can run it without an editor.
 */

export interface RemovalTarget {
  sectionTitle: string;
  content: string;
}

export interface Range {
  from: number;
  to: number;
}

const normalize = (s: string) => s.replace(/\s+/g, " ").trim().slice(0, 120);

/** Ranges in the order found; delete them bottom-up. */
export function planRemovals(doc: any, requests: RemovalTarget[]): Range[] {
  const targets = requests.map((r) => ({
    sectionTitle: normalize(r.sectionTitle),
    content: normalize(r.content),
  }));

  const ranges: Range[] = [];
  let currentSectionTitle = "";
  let section: (Range & { removed: number; kept: number }) | null = null;
  const dropIfEmptied = () => {
    if (section && section.removed > 0 && section.kept === 0) {
      ranges.push({ from: section.from, to: section.to });
    }
  };

  doc.descendants((node: any, pos: number) => {
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
    const hit = targets.some(
      (t) =>
        (t.sectionTitle === "" || t.sectionTitle === currentSectionTitle) &&
        nodeText.startsWith(t.content.slice(0, 60)),
    );
    if (hit) {
      ranges.push({ from: pos, to: pos + node.nodeSize });
      if (section) section.removed += 1;
    } else if (section) {
      section.kept += 1;
    }
  });
  dropIfEmptied();

  return ranges;
}
