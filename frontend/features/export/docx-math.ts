/**
 * LaTeX as a Word equation.
 *
 * The editor stores math as LaTeX and draws it with KaTeX. A Word file that
 * printed `\(\sqrt{49} + 2^3\)` would hand the teacher markup to retype, so
 * the common school subset is rebuilt as native Word math (OMML): fractions,
 * roots, powers and subscripts, Greek letters, operators and relations.
 * Anything this does not know prints as its own name, and anything it cannot
 * parse prints as the LaTeX itself — never an exception, never lost.
 *
 * Pure, so `scripts/test-docx-paper.mjs` can run it without a browser.
 */

import {
  MathFraction,
  MathRadical,
  MathRun,
  MathSubScript,
  MathSubSuperScript,
  MathSuperScript,
  type MathComponent,
} from "docx";

const SYMBOLS: Record<string, string> = {
  alpha: "α", beta: "β", gamma: "γ", delta: "δ", epsilon: "ε", varepsilon: "ε",
  zeta: "ζ", eta: "η", theta: "θ", vartheta: "ϑ", iota: "ι", kappa: "κ",
  lambda: "λ", mu: "μ", nu: "ν", xi: "ξ", pi: "π", rho: "ρ", sigma: "σ",
  tau: "τ", upsilon: "υ", phi: "φ", varphi: "φ", chi: "χ", psi: "ψ", omega: "ω",
  Gamma: "Γ", Delta: "Δ", Theta: "Θ", Lambda: "Λ", Xi: "Ξ", Pi: "Π",
  Sigma: "Σ", Phi: "Φ", Psi: "Ψ", Omega: "Ω",
  times: "×", div: "÷", pm: "±", mp: "∓", cdot: "·", ast: "∗", star: "⋆",
  bullet: "•", circ: "∘", degree: "°",
  le: "≤", leq: "≤", ge: "≥", geq: "≥", ne: "≠", neq: "≠", approx: "≈",
  equiv: "≡", sim: "∼", cong: "≅", propto: "∝", ll: "≪", gg: "≫",
  infty: "∞", partial: "∂", nabla: "∇", sum: "∑", prod: "∏", int: "∫",
  angle: "∠", triangle: "△", perp: "⊥", parallel: "∥", therefore: "∴",
  because: "∵", in: "∈", notin: "∉", subset: "⊂", subseteq: "⊆",
  supset: "⊃", cup: "∪", cap: "∩", emptyset: "∅", varnothing: "∅",
  forall: "∀", exists: "∃", neg: "¬", land: "∧", lor: "∨",
  to: "→", rightarrow: "→", leftarrow: "←", leftrightarrow: "↔",
  Rightarrow: "⇒", Leftarrow: "⇐", Leftrightarrow: "⇔", implies: "⇒",
  iff: "⇔", uparrow: "↑", downarrow: "↓",
  ldots: "…", cdots: "⋯", dots: "…", prime: "′",
  langle: "⟨", rangle: "⟩", lbrace: "{", rbrace: "}", vert: "|", mid: "|",
  lvert: "|", rvert: "|", backslash: "\\",
  quad: " ", qquad: "  ",
};

/** Upright function names: `\sin x` prints "sin x", not "sinx" in italics. */
const FUNCTIONS = new Set([
  "sin", "cos", "tan", "cot", "sec", "csc", "arcsin", "arccos", "arctan",
  "sinh", "cosh", "tanh", "log", "ln", "lg", "exp", "lim", "max", "min",
  "det", "gcd", "deg",
]);

/** Commands whose argument is printed as it stands. */
const TEXT_COMMANDS = new Set([
  "text", "textrm", "textbf", "textit", "mathrm", "mathbf", "mathit",
  "operatorname", "mbox",
]);

/** Accents Word math has no simple form for here: the argument alone. */
const ACCENTS = new Set(["overline", "underline", "bar", "vec", "hat", "tilde", "dot", "widehat", "overrightarrow"]);

/** One printed unit: plain text (which merges with its neighbours) or a built piece. */
interface Atom {
  parts: MathComponent[];
  text?: string;
  sub?: MathComponent[];
  sup?: MathComponent[];
}

class Parser {
  private i = 0;

  constructor(private readonly s: string) {}

  /** Everything up to `stop` (consumed) or the end. */
  parse(stop?: string): MathComponent[] {
    const atoms: Atom[] = [];
    while (this.i < this.s.length) {
      const ch = this.s[this.i];
      if (stop && ch === stop) {
        this.i += 1;
        return flatten(atoms);
      }
      if (ch === "^" || ch === "_") {
        this.i += 1;
        const script = this.argument();
        const base = atoms.pop() ?? { parts: [] };
        // A script binds to one character of a plain run, as in TeX: "10^3"
        // raises only the 3's base digit 0, which prints as "10³".
        if (base.text && base.text.length > 1 && !base.sub && !base.sup) {
          const rest = base.text.slice(0, -1);
          atoms.push({ parts: [new MathRun(rest)], text: rest });
          const last = base.text.slice(-1);
          atoms.push({ parts: [new MathRun(last)], text: last, [ch === "^" ? "sup" : "sub"]: script });
        } else {
          atoms.push({ ...base, [ch === "^" ? "sup" : "sub"]: script });
        }
        continue;
      }
      if (/\s/.test(ch)) {
        this.i += 1;
        continue;
      }
      if (ch === "{") {
        this.i += 1;
        atoms.push({ parts: this.parse("}") });
        continue;
      }
      if (ch === "\\") {
        atoms.push({ parts: this.command() });
        continue;
      }
      if (ch === "~") {
        this.i += 1;
        atoms.push({ parts: [new MathRun(" ")] });
        continue;
      }
      if (ch === "'") {
        this.i += 1;
        atoms.push({ parts: [new MathRun("′")], text: "′" });
        continue;
      }
      this.i += 1;
      const previous = atoms[atoms.length - 1];
      if (previous?.text !== undefined && !previous.sub && !previous.sup) {
        previous.text += ch;
        previous.parts = [new MathRun(previous.text)];
      } else {
        atoms.push({ parts: [new MathRun(ch)], text: ch });
      }
    }
    if (stop) throw new Error(`unclosed ${stop}`);
    return flatten(atoms);
  }

  /** One argument: a braced group, a command, or a single character. */
  private argument(): MathComponent[] {
    while (/\s/.test(this.s[this.i] ?? "")) this.i += 1;
    const ch = this.s[this.i];
    if (ch === undefined) throw new Error("missing argument");
    if (ch === "{") {
      this.i += 1;
      return this.parse("}");
    }
    if (ch === "\\") return this.command();
    this.i += 1;
    return [new MathRun(ch)];
  }

  /** The raw text of a braced argument, for `\text{…}`. */
  private rawArgument(): string {
    while (/\s/.test(this.s[this.i] ?? "")) this.i += 1;
    if (this.s[this.i] !== "{") return this.s[this.i++] ?? "";
    let depth = 0;
    const start = this.i + 1;
    for (; this.i < this.s.length; this.i += 1) {
      if (this.s[this.i] === "{") depth += 1;
      if (this.s[this.i] === "}" && --depth === 0) {
        this.i += 1;
        return this.s.slice(start, this.i - 1);
      }
    }
    throw new Error("unclosed {");
  }

  private command(): MathComponent[] {
    this.i += 1; // the backslash
    const letters = /^[A-Za-z]+/.exec(this.s.slice(this.i));
    const name = letters ? letters[0] : (this.s[this.i] ?? "");
    this.i += name.length;

    if (name === "frac" || name === "dfrac" || name === "tfrac") {
      const numerator = this.argument();
      const denominator = this.argument();
      return [new MathFraction({ numerator, denominator })];
    }
    if (name === "sqrt") {
      let degree: MathComponent[] | undefined;
      while (/\s/.test(this.s[this.i] ?? "")) this.i += 1;
      if (this.s[this.i] === "[") {
        this.i += 1;
        degree = this.parse("]");
      }
      return [new MathRadical({ children: this.argument(), degree })];
    }
    if (name === "left" || name === "right" || name === "big" || name === "Big") {
      while (/\s/.test(this.s[this.i] ?? "")) this.i += 1;
      // "\left." is an invisible delimiter.
      if (this.s[this.i] === ".") {
        this.i += 1;
        return [];
      }
      return this.s[this.i] === "\\" ? this.command() : [new MathRun(this.s[this.i++] ?? "")];
    }
    if (TEXT_COMMANDS.has(name)) return [new MathRun(this.rawArgument())];
    if (ACCENTS.has(name)) return this.argument();
    if (FUNCTIONS.has(name)) return [new MathRun(name)];
    if (name in SYMBOLS) return [new MathRun(SYMBOLS[name])];
    // `\%`, `\{` and friends are the character; `\,` `\;` `\\` are space.
    if (!letters) return [new MathRun(",;:!\\".includes(name) ? " " : name)];
    return [new MathRun(name)];
  }
}

function flatten(atoms: Atom[]): MathComponent[] {
  const out: MathComponent[] = [];
  for (const atom of atoms) {
    if (atom.sub && atom.sup) {
      out.push(new MathSubSuperScript({ children: atom.parts, subScript: atom.sub, superScript: atom.sup }));
    } else if (atom.sup) {
      out.push(new MathSuperScript({ children: atom.parts, superScript: atom.sup }));
    } else if (atom.sub) {
      out.push(new MathSubScript({ children: atom.parts, subScript: atom.sub }));
    } else {
      out.push(...atom.parts);
    }
  }
  return out;
}

/** The pieces of a Word equation for `latex`; the LaTeX itself if it will not parse. */
export function latexToMath(latex: string): MathComponent[] {
  const source = String(latex || "").trim();
  if (!source) return [];
  // Matrices, cases and aligned blocks have no counterpart here.
  if (source.includes("\\begin")) return [new MathRun(source)];
  try {
    return new Parser(source).parse();
  } catch {
    return [new MathRun(source)];
  }
}
