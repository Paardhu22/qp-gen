/**
 * The chat's starter prompts, chosen from what the teacher actually has.
 *
 * They were four hardcoded strings, identical for every teacher forever. That
 * made them useless twice over: they never reflected the work already in the
 * account, and they never mentioned that templates, the question bank or saved
 * blueprints exist. The dashboard chat is the app's only discovery surface, so
 * a teacher who lives in it could use the product for months without learning
 * the rest of it is there.
 *
 * ## Always one door out
 *
 * `pickSuggestions` returns four, and reserves at least one slot for a surface
 * the teacher has **not** used yet. Prompts drawn from existing work are the
 * more immediately useful ones, so without that reservation they would win
 * every slot and the discovery job would quietly stop happening for exactly
 * the established users who have the most left to find.
 */

export interface TeacherInventory {
  paperCount: number;
  templateCount: number;
  bankQuestionCount: number;
  /** Most recent paper's subject/class, when there is one, for a warmer prompt. */
  recentPaperTitle?: string | null;
}

/** Shown when the inventory could not be loaded — the original four. */
export const FALLBACK_SUGGESTIONS = [
  "Make a class 10 Science unit test on Light.",
  "What does the class 10 English paper look like?",
  "Draft a note to parents about the term test.",
  "Explain the CBSE competency-based question format.",
];

const DISCOVERY = {
  templates:
    "How do paper templates work, and should I save one?",
  bank: "What is the question bank, and how do questions get into it?",
  blueprint: "Walk me through building a paper blueprint section by section.",
} as const;

export function pickSuggestions(inventory: TeacherInventory | null): string[] {
  if (!inventory) return FALLBACK_SUGGESTIONS;

  const { paperCount, templateCount, bankQuestionCount, recentPaperTitle } =
    inventory;

  // Prompts that lean on work the teacher has already done.
  const grounded: string[] = [];
  if (recentPaperTitle) {
    grounded.push(`Make another paper like "${recentPaperTitle}".`);
  }
  if (templateCount > 0) {
    grounded.push("Start a paper from one of my saved templates.");
  }
  if (bankQuestionCount > 0) {
    grounded.push(
      `Build a paper from the ${bankQuestionCount} questions in my bank.`,
    );
  }
  if (paperCount > 0) {
    grounded.push("Make a second set of my last paper, same difficulty.");
  }

  // Surfaces this teacher has not touched. At least one of these always ships.
  const undiscovered: string[] = [];
  if (templateCount === 0) undiscovered.push(DISCOVERY.templates);
  if (bankQuestionCount === 0) undiscovered.push(DISCOVERY.bank);
  if (paperCount === 0) undiscovered.push(DISCOVERY.blueprint);

  // A brand-new account has nothing to ground a prompt in, so it gets the
  // original starters — written to show what the generator can do, which is
  // exactly what someone with an empty account needs to see.
  if (grounded.length === 0) {
    return [...undiscovered, ...FALLBACK_SUGGESTIONS].slice(0, 4);
  }

  const reserved = undiscovered.slice(0, 1);
  const rest = [...grounded, ...undiscovered.slice(1), ...FALLBACK_SUGGESTIONS];

  const out: string[] = [];
  for (const s of [...reserved, ...rest]) {
    if (out.length === 4) break;
    if (!out.includes(s)) out.push(s);
  }
  return out;
}
