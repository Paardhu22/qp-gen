/**
 * The difficulty slider, as numbers.
 *
 * A paper's difficulty is a level from 0 (gentle) to 100 (demanding). The level
 * fixes the *mix* of the paper — what share of its questions are basic,
 * moderate and challenging — and the backend deals that mix out to the
 * individual questions (`backend/services/generation/difficulty.py`). This file
 * is the slider's preview of the same curve, so what the teacher sees under the
 * slider is what the generator will aim for.
 *
 * `ANCHORS` mirrors the backend table. They are the one thing that is written
 * twice, and `services/generation/tests/test_difficulty.py` fails if they
 * drift, so change both together.
 */

export type Tier = "easy" | "medium" | "hard";
export type Shares = Record<Tier, number>;
type Band = "1-2" | "3-5" | "6-8" | "9-10";
type Anchor = readonly [number, number, number];

export const TIERS: readonly Tier[] = ["easy", "medium", "hard"];
export const DEFAULT_LEVEL = 50;

/** What the old three-way switch means on the slider. */
export const LABEL_LEVELS: Record<Tier, number> = { easy: 15, medium: 50, hard: 85 };

// (easy, medium, hard) at the bottom, middle and top of the slider, by class band.
export const ANCHORS: Record<Band, { low: Anchor; mid: Anchor; high: Anchor }> = {
  "1-2": { low: [0.78, 0.22, 0.0], mid: [0.55, 0.4, 0.05], high: [0.4, 0.48, 0.12] },
  "3-5": { low: [0.68, 0.28, 0.04], mid: [0.4, 0.45, 0.15], high: [0.22, 0.46, 0.32] },
  "6-8": { low: [0.62, 0.31, 0.07], mid: [0.35, 0.48, 0.17], high: [0.15, 0.45, 0.4] },
  "9-10": { low: [0.58, 0.34, 0.08], mid: [0.3, 0.5, 0.2], high: [0.12, 0.43, 0.45] },
};

export function classBand(classNum?: number | string | null): Band {
  const n = typeof classNum === "string" ? parseInt(classNum.replace(/\D/g, ""), 10) : classNum;
  if (typeof n !== "number" || !Number.isFinite(n)) return "9-10";
  if (n <= 2) return "1-2";
  if (n <= 5) return "3-5";
  if (n <= 8) return "6-8";
  return "9-10";
}

/** Any way a difficulty may be stated, as a level from 0 to 100. */
export function normalizeLevel(value: unknown, fallback: number = DEFAULT_LEVEL): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.max(0, Math.min(100, Math.round(value)));
  }
  if (typeof value === "string") {
    const text = value.trim().toLowerCase();
    if (text in LABEL_LEVELS) return LABEL_LEVELS[text as Tier];
    if (text !== "" && Number.isFinite(Number(text))) {
      return Math.max(0, Math.min(100, Math.round(Number(text))));
    }
  }
  return fallback;
}

/** `easy` / `medium` / `hard` for a level: the tag stored on a paper and read by older code. */
export function labelForLevel(level: number): Tier {
  const n = normalizeLevel(level);
  if (n < 34) return "easy";
  if (n < 67) return "medium";
  return "hard";
}

/** The share of basic, moderate and challenging questions at a level. */
export function sharesFor(level: number, classNum?: number | string | null): Shares {
  const n = normalizeLevel(level);
  const a = ANCHORS[classBand(classNum)];
  const [from, to, t] = n <= 50 ? [a.low, a.mid, n / 50] : [a.mid, a.high, (n - 50) / 50];
  const mix = from.map((x, i) => x + (to[i] - x) * t);
  return { easy: mix[0], medium: mix[1], hard: mix[2] };
}

/** The mix as whole percentages that add up to exactly 100. */
export function mixPercents(level: number, classNum?: number | string | null): Shares {
  const shares = sharesFor(level, classNum);
  const raw = TIERS.map((tier) => shares[tier] * 100);
  const floors = raw.map(Math.floor);
  let spare = 100 - floors.reduce((sum, n) => sum + n, 0);
  const byRemainder = raw
    .map((value, i) => ({ i, rest: value - floors[i] }))
    .sort((p, q) => q.rest - p.rest || (p.i === 1 ? -1 : 1));
  for (const { i } of byRemainder) {
    if (spare <= 0) break;
    floors[i] += 1;
    spare -= 1;
  }
  return { easy: floors[0], medium: floors[1], hard: floors[2] };
}

/** A word for the level, for the slider's readout. */
export function describeLevel(level: number): string {
  const n = normalizeLevel(level);
  if (n < 15) return "Gentle";
  if (n < 35) return "Easier";
  if (n < 65) return "Balanced";
  if (n < 85) return "Harder";
  return "Demanding";
}

/** What a level means for the paper, in a sentence. */
export function explainLevel(level: number): string {
  const n = normalizeLevel(level);
  if (n < 35) return "Mostly straightforward questions that test the basics.";
  if (n < 65) return "A balanced mix of basic, moderate and challenging questions.";
  return "More questions that need reasoning, several steps or more than one concept.";
}
