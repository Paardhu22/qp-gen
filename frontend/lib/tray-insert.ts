/**
 * Moving review-tray items into the paper.
 *
 * Shared by the tray's own buttons and by the editor page, which inserts a
 * finished run's questions automatically. One path, so an auto-inserted
 * paper is laid out exactly like one inserted by "Insert all" — same section
 * grouping, same slot order — and the tray's Undo works on both.
 */

import { useEditorStore, type TrayItem } from "@/store/editor-store";

export function groupBySection(items: TrayItem[]) {
  const map = new Map<string, TrayItem[]>();
  for (const item of items) {
    const list = map.get(item.sectionTitle) || [];
    list.push(item);
    map.set(item.sectionTitle, list);
  }
  // Generation is parallel, so items arrive in completion order. The
  // backend stamps metadata.slotIndex with the blueprint position —
  // sort by it so inserts respect the plan layout (e.g. Maths Section A
  // must end with the two Assertion-Reason questions at Q19–Q20).
  for (const list of map.values()) {
    list.sort(
      (a, b) =>
        (Number(a.question.metadata?.slotIndex) || Number.MAX_SAFE_INTEGER) -
        (Number(b.question.metadata?.slotIndex) || Number.MAX_SAFE_INTEGER),
    );
  }
  return Array.from(map.entries());
}

/**
 * Insert the given tray items that are still pending. Returns how many were
 * inserted; already-inserted and unknown ids are skipped.
 */
export function insertTrayItems(ids: string[]): number {
  const { generatedTray, appendSections, markTrayInserted } =
    useEditorStore.getState();
  const wanted = new Set(ids);
  const items = generatedTray.filter((t) => wanted.has(t.id) && !t.inserted);
  if (items.length === 0) return 0;

  // Each section is committed as ONE `appendSections` entry so the section
  // header and its questions land atomically in the editor's insertion effect
  // (queueMicrotask). Otherwise re-numbering races with inserts.
  appendSections(
    groupBySection(items).map(([title, sectionItems]) => ({
      title,
      questions: sectionItems.map((t) => ({
        content: t.question.content,
        type: t.question.type,
        typeCode: t.question.typeCode,
        options: t.question.options || [],
        answer: t.question.answer,
        marks: t.question.marks,
        image_url: t.question.image_url,
        metadata: t.question.metadata,
      })),
    })),
  );
  markTrayInserted(items.map((t) => t.id));
  return items.length;
}
