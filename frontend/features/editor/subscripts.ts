/**
 * Indexed variables as maths: `x1` → `\(x_{1}\)`.
 *
 * The twin of `backend/services/generation/rules/subscripts.py`, and meant to
 * stay line-for-line comparable with it. The backend scrubs what it generates;
 * this runs when text becomes editor nodes, so a question that was banked
 * before the scrub existed, or arrived by any other route, still prints x₁
 * and not "x1". Both are tested against the same hand-written case table
 * (`backend/services/generation/rules/tests/subscript_cases.json`), by
 * `scripts/test-subscripts.mjs` here and `test_subscripts.py` there.
 *
 * It is deliberately NOT "any letter followed by a digit": `A1` is a
 * spreadsheet cell, `O2` is oxygen, `6x2` is six x-squared. A token converts
 * only on evidence that it is an index (see the backend module for the full
 * argument):
 *
 *  - explicit     x_1, x_{12}, a_n
 *  - tuple        (x1, y1)
 *  - run          x1x2, P1P2
 *  - coefficient  a1x, as in a1x + b1y + c1 = 0
 *  - family       one letter seen with two indices, the smallest 0 or 1
 *  - lone         a single lowercase x1 / a0 — Mathematics only
 *
 * and how much of that is trusted depends on the subject.
 */

export interface IndexPolicy {
  name: "maths" | "science" | "default" | "off";
  /** May a lowercase letter be an index base (x1)? */
  lower: boolean;
  /** May an uppercase one (P1)? */
  upper: boolean;
  /** Is a lone x1 / a0 enough, with no sibling for evidence? */
  lone: boolean;
  /** Skip uppercase element letters (O2, N2, H2) when the text is chemistry. */
  chemistryGuard: boolean;
}

const MATHS: IndexPolicy = { name: "maths", lower: true, upper: true, lone: true, chemistryGuard: false };
const SCIENCE: IndexPolicy = { name: "science", lower: true, upper: true, lone: false, chemistryGuard: true };
const DEFAULT: IndexPolicy = { name: "default", lower: true, upper: false, lone: false, chemistryGuard: false };
const OFF: IndexPolicy = { name: "off", lower: false, upper: false, lone: false, chemistryGuard: false };

/** First words of subjects where `A1`, `h1`, `x86` mean something else. */
const OFF_FIRST_WORDS = new Set([
  "english", "hindi", "telugu", "sanskrit", "urdu", "tamil", "kannada",
  "malayalam", "marathi", "bengali", "punjabi", "gujarati", "odia",
  "assamese", "french", "german", "spanish", "social", "history",
  "geography", "civics", "economics", "political", "computer", "computers",
  "ict", "informatics", "information", "python", "coding", "programming",
]);
const SCIENCE_WORDS = ["science", "physics", "chemistry", "biology"];

/** The trust a subject earns. Missing or empty is the cautious default. */
export function policyFor(subject?: string | null): IndexPolicy {
  const lower = String(subject ?? "").trim().toLowerCase();
  if (!lower) return DEFAULT;
  if (lower.includes("math") || lower.includes("statistic")) return MATHS;
  const words = lower.replace(/&/g, " ").split(/\s+/).filter(Boolean);
  if ((words.length > 0 && OFF_FIRST_WORDS.has(words[0])) || lower.includes("social")) return OFF;
  if (SCIENCE_WORDS.some((word) => lower.includes(word))) return SCIENCE;
  return DEFAULT;
}

// ── Recognising indexed variables ────────────────────────────────────────
//
// Built from strings, not literals: the project targets ES2017, where the
// compiler rejects lookbehind in a regex literal. Every runtime we ship to
// supports it.

/** An index written bare: 0, or 1–99 without a leading zero. */
const DIGITS = String.raw`(?:0|[1-9]\d?)`;
/** What may not touch a token on its left: a longer word, a LaTeX command, a
 *  file name, an e-mail, an HTML tag, a hex colour, a price. A number may:
 *  `3x1` is three times x₁. */
const LEFT = String.raw`(?<![A-Za-z_\\.@#<$])`;
/** Nor on the right: `x1y` is a word, `x1.txt` a file, `x1.5` a decimal. */
const RIGHT = String.raw`(?![A-Za-z0-9_]|\.[A-Za-z0-9])`;

const BARE = String.raw`[A-Za-z]${DIGITS}`;
const EXPLICIT = String.raw`[A-Za-z]_(?:${DIGITS}|\{[A-Za-z0-9]{1,3}\}|[ijkn])`;
const ANY = String.raw`(?:${EXPLICIT}|${BARE})`;

const PATTERN_SOURCE = [
  // (x1, y1) — two to four indexed variables in brackets.            [1]
  String.raw`(\(\s*${ANY}(?:\s*,\s*${ANY}){1,3}\s*\))`,
  // x1x2, P1P2 — indexed variables side by side.                      [2]
  String.raw`(${LEFT}(?:${BARE}){2,3}${RIGHT})`,
  // x_1, a_n — already written as a subscript, just not typeset.      [3]
  String.raw`(${LEFT}${EXPLICIT}${RIGHT})`,
  // a1x — an indexed coefficient and its variable.                    [4]
  String.raw`(${LEFT}${BARE}[xyz]${RIGHT})`,
  // x1                                                                [5]
  String.raw`(${LEFT}${BARE}${RIGHT})`,
].join("|");

type Kind = "tuple" | "run" | "explicit" | "coef" | "bare";
const KINDS: Kind[] = ["tuple", "run", "explicit", "coef", "bare"];

function kindOf(groups: (string | undefined)[]): Kind {
  const at = groups.findIndex((g) => g !== undefined);
  return KINDS[at];
}

const MATH_SPAN = /\\\([\s\S]*?\\\)|\\\[[\s\S]*?\\\]/g;
const BARE_TOKEN = new RegExp(String.raw`^([A-Za-z])(${DIGITS})$`);
const EXPLICIT_TOKEN = new RegExp(String.raw`^([A-Za-z])_(\{[A-Za-z0-9]{1,3}\}|${DIGITS}|[ijkn])$`);
const COEF_TOKEN = new RegExp(String.raw`^([A-Za-z])(${DIGITS})([xyz])$`);
/** Inside an existing math span: x_1, x_{12} — evidence only, never rewritten. */
const SPAN_SUBSCRIPT = String.raw`(?<![A-Za-z\\])([A-Za-z])_\{?(${DIGITS})\}?`;

/** Single-letter chemical elements, the letters O2 / N2 / H2 share with
 *  physics' R, V, I and maths' P. */
const ELEMENT_LETTERS = new Set("HBCNOFPSKVYIWU".split(""));
const CHEMISTRY = new RegExp(
  String.raw`\b(?:molecules?|atoms?|atomic|compounds?|elements?|react\w*|` +
    String.raw`oxide|oxygen|hydrogen|nitrogen|carbon|sulphur|sulfur|chlorine|acids?|` +
    String.raw`bases?|salts?|moles?|valen\w+|bonds?|bonding|ions?|ionic|chemical|periodic|` +
    String.raw`isotopes?|allotropes?|ozone|mixture|solution|catalyst|combustion|` +
    String.raw`electrolysis|alkali)\b|→|->`,
  "i",
);

function latex(token: string): string {
  const explicit = EXPLICIT_TOKEN.exec(token);
  if (explicit) return `${explicit[1]}_{${explicit[2].replace(/[{}]/g, "")}}`;
  const bare = BARE_TOKEN.exec(token);
  if (bare) return `${bare[1]}_{${bare[2]}}`;
  const coefficient = COEF_TOKEN.exec(token);
  if (coefficient) return `${coefficient[1]}_{${coefficient[2]}}${coefficient[3]}`;
  return token;
}

function tupleLatex(group: string): string {
  const members = group
    .slice(1, -1)
    .split(",")
    .map((member) => latex(member.trim()));
  return `\\((${members.join(", ")})\\)`;
}

function letterAllowed(letter: string, policy: IndexPolicy, chemistry: boolean): boolean {
  if (/[a-z]/.test(letter)) return policy.lower;
  if (!policy.upper) return false;
  return !(policy.chemistryGuard && chemistry && ELEMENT_LETTERS.has(letter));
}

function indexOf(token: string): number {
  const found = /^(?:0|[1-9]\d?)/.exec(token.slice(1));
  return found ? parseInt(found[0], 10) : NaN;
}

function addSeen(seen: Map<string, Set<number>>, letter: string, index: number) {
  let set = seen.get(letter);
  if (!set) seen.set(letter, (set = new Set()));
  set.add(index);
}

/**
 * Rewrite indexed variables outside existing maths as `\( x_{1} \)`.
 *
 * Existing `\( … \)` / `\[ … \]` spans are never touched, so the pass is
 * idempotent and safe on text a model already typeset.
 */
export function typesetIndices(text: string, subject?: string | null): string {
  if (!text || !/[A-Za-z](?:_|\d)/.test(text)) return text;

  const policy = policyFor(subject);
  const spans = Array.from(text.matchAll(new RegExp(MATH_SPAN.source, "g")));
  const outside: string[] = [];
  let cursor = 0;
  for (const span of spans) {
    outside.push(text.slice(cursor, span.index));
    cursor = (span.index as number) + span[0].length;
  }
  outside.push(text.slice(cursor));
  const plain = outside.join("\n");

  // What each letter has been seen indexed with, bare or already typeset.
  const seen = new Map<string, Set<number>>();
  const spanText = spans.map((m) => m[0]).join("\n");
  const spanSubscript = new RegExp(SPAN_SUBSCRIPT, "g");
  for (let m = spanSubscript.exec(spanText); m; m = spanSubscript.exec(spanText)) {
    addSeen(seen, m[1], parseInt(m[2], 10));
  }

  const chemistry = CHEMISTRY.test(text);
  /** Letters proven an index by their shape: a tuple, a run, an explicit x_1. */
  const structural = new Set<string>();
  /** Letters that may be, by company (a family) or by being alone (Maths). */
  const soft = new Set<string>();
  const bare: string[] = [];

  const scan = new RegExp(PATTERN_SOURCE, "g");
  for (let match = scan.exec(plain); match; match = scan.exec(plain)) {
    const token = match[0];
    const kind = kindOf(match.slice(1));
    if (kind === "tuple") {
      const members = token.slice(1, -1).split(",").map((m) => m.trim());
      if (members.every((m) => m.includes("_") || letterAllowed(m[0], policy, chemistry))) {
        members.forEach((m) => structural.add(m[0]));
      }
    } else if (kind === "run") {
      const pieces = token.match(new RegExp(BARE, "g")) ?? [];
      if (pieces.every((p) => letterAllowed(p[0], policy, chemistry))) {
        pieces.forEach((p) => structural.add(p[0]));
      }
    } else if (kind === "explicit") {
      const explicit = EXPLICIT_TOKEN.exec(token)!;
      const sub = explicit[2].replace(/[{}]/g, "");
      if (/^\d+$/.test(sub)) addSeen(seen, explicit[1], parseInt(sub, 10));
      structural.add(explicit[1]);
    } else if (letterAllowed(token[0], policy, chemistry)) {
      addSeen(seen, token[0], indexOf(token));
      bare.push(token);
    }
  }

  for (const token of bare) {
    const letter = token[0];
    const index = indexOf(token);
    const indices = Array.from(seen.get(letter) ?? []);
    if (indices.length >= 2 && Math.min(...indices) <= 1) {
      soft.add(letter);
    } else if (policy.lone && /[a-z]/.test(letter) && (index === 0 || index === 1)) {
      soft.add(letter);
    }
  }

  // No guard for "6x2" being six x-squared: a family needs an index of 0 or 1
  // and no one writes x1 as an exponent, so a polynomial never gets this far.
  const qualifying = (letter: string) => structural.has(letter) || soft.has(letter);

  const rewrite = (segment: string): string =>
    segment.replace(new RegExp(PATTERN_SOURCE, "g"), (token: string, ...groups: any[]) => {
      const kind = kindOf(groups.slice(0, 5));
      if (kind === "tuple") {
        const members = token.slice(1, -1).split(",").map((m) => m.trim());
        return members.every((m) => m.includes("_") || qualifying(m[0])) ? tupleLatex(token) : token;
      }
      if (kind === "run") {
        const pieces = token.match(new RegExp(BARE, "g")) ?? [];
        return pieces.every((p) => qualifying(p[0]))
          ? `\\(${pieces.map(latex).join("")}\\)`
          : token;
      }
      if (kind === "explicit") return `\\(${latex(token)}\\)`;
      return qualifying(token[0]) ? `\\(${latex(token)}\\)` : token;
    });

  let out = "";
  cursor = 0;
  for (const span of spans) {
    out += rewrite(text.slice(cursor, span.index)) + span[0];
    cursor = (span.index as number) + span[0].length;
  }
  return out + rewrite(text.slice(cursor));
}
