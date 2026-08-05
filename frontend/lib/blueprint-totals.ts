import type { Blueprint, BlueprintSlot } from "@/lib/api-client";

/**
 * Derive a blueprint's totals from its slots.
 *
 * The server computes these too, and deliberately never echoes back a total the
 * client sent — a blueprint claiming "80 marks" while its slots add to 83 would
 * print a paper whose header contradicts its own contents. This is the same
 * arithmetic on the client, for the same reason: so an editing surface can show
 * live totals per keystroke without a round trip, and so the number on screen is
 * always derived from the slots on screen rather than from a stale response.
 *
 * Keep it a pure function of `slots`. The moment a total comes from anywhere
 * else, there are two sources of truth again.
 */
export function recomputeTotals(slots: BlueprintSlot[]): Blueprint {
  const byType: Record<string, number> = {};
  const sectionOrder: string[] = [];
  const bySectionMap = new Map<string, { questions: number; marks: number }>();

  for (const slot of slots) {
    byType[slot.questionType] = (byType[slot.questionType] ?? 0) + 1;
    if (!bySectionMap.has(slot.sectionTitle)) {
      bySectionMap.set(slot.sectionTitle, { questions: 0, marks: 0 });
      sectionOrder.push(slot.sectionTitle);
    }
    const entry = bySectionMap.get(slot.sectionTitle)!;
    entry.questions += 1;
    entry.marks += slot.marks;
  }

  return {
    slots,
    totalQuestions: slots.length,
    totalMarks: slots.reduce((sum, s) => sum + s.marks, 0),
    generatedCount: slots.filter((s) => s.source === "generate").length,
    savedCount: slots.filter((s) => s.source === "saved").length,
    byType,
    bySection: sectionOrder.map((title) => ({
      title,
      ...bySectionMap.get(title)!,
    })),
  };
}
