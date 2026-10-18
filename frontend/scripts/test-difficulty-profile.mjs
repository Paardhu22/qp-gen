#!/usr/bin/env node
// The difficulty slider — run from frontend/:
//   node scripts/test-difficulty-profile.mjs
//
// `difficulty-profile.ts` is the browser's copy of the level → mix curve that
// the backend uses (`backend/services/generation/difficulty.py`); the slider
// previews it. The backend's own test fails if the anchor tables drift; this
// holds the curve's behaviour and the slider's markup.

import { fileURLToPath } from "node:url";
import path from "node:path";
import { createJiti } from "jiti";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const jiti = createJiti(here, {
  interopDefault: true,
  jsx: true,
  extensions: [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"],
  alias: { "@": root },
});

const P = await jiti.import(path.join(root, "features/generation/difficulty-profile.ts"));
const { DifficultySlider } = await jiti.import(path.join(root, "features/generation/difficulty-slider.tsx"));
const { createElement } = await import("react");
const { renderToStaticMarkup } = await import("react-dom/server");

let failures = 0;
function check(label, condition, detail = "") {
  if (condition) console.log(`PASS  ${label}`);
  else {
    failures += 1;
    console.error(`FAIL  ${label}${detail ? ` — ${detail}` : ""}`);
  }
}
const near = (a, b, eps = 1e-9) => Math.abs(a - b) < eps;
const BANDS = [1, 4, 7, 10];

// ── Levels ───────────────────────────────────────────────────────────────
check("numbers are clamped and rounded", P.normalizeLevel(72.6) === 73 && P.normalizeLevel(-5) === 0 && P.normalizeLevel(400) === 100);
check("numeric strings are levels", P.normalizeLevel("35") === 35);
check("the old labels map to their anchors", P.normalizeLevel("easy") === 15 && P.normalizeLevel("Medium") === 50 && P.normalizeLevel(" HARD ") === 85);
check("anything unreadable is the default, not an error", [undefined, null, "", "tricky", {}, NaN].every((v) => P.normalizeLevel(v) === 50));
check(
  "the label follows the level (same thresholds as the backend)",
  [0, 33, 34, 66, 67, 100].map(P.labelForLevel).join() === "easy,easy,medium,medium,hard,hard",
);

// ── The curve ────────────────────────────────────────────────────────────
{
  let ok = true;
  let detail = "";
  for (const band of BANDS) {
    for (let level = 0; level <= 100; level += 1) {
      const s = P.sharesFor(level, band);
      const sum = s.easy + s.medium + s.hard;
      if (!near(sum, 1, 1e-6) || s.easy < 0 || s.medium < 0 || s.hard < 0) {
        ok = false;
        detail = `band ${band} level ${level}: ${JSON.stringify(s)}`;
      }
    }
  }
  check("shares always sum to 1 and are never negative", ok, detail);
}
{
  const mid = P.sharesFor(50, 10);
  check("the middle of the slider is the board year's balanced mix", near(mid.easy, 0.3) && near(mid.medium, 0.5) && near(mid.hard, 0.2));
  const low = P.sharesFor(0, 10);
  const high = P.sharesFor(100, 10);
  check("the bottom is mostly straightforward", low.easy + low.medium > 0.85);
  check("the top never passes 45% challenging and keeps basic questions", high.hard <= 0.45 + 1e-9 && high.easy >= 0.12 - 1e-9);
  check("the top really differs from the bottom", high.hard / low.hard >= 4 && low.easy / high.easy >= 4);
  const q = P.sharesFor(75, 10);
  check("a point between anchors is interpolated (75 → halfway from middle to top)", near(q.easy, 0.21) && near(q.medium, 0.465) && near(q.hard, 0.325), JSON.stringify(q));
}
{
  let monotone = true;
  for (const band of BANDS) {
    let prev = P.sharesFor(0, band);
    for (let level = 1; level <= 100; level += 1) {
      const cur = P.sharesFor(level, band);
      if (cur.hard < prev.hard - 1e-9 || cur.easy > prev.easy + 1e-9) monotone = false;
      prev = cur;
    }
  }
  check("raising the slider only ever raises the challenging share and lowers the basic one", monotone);
}
check("younger classes lean easier at the same level", P.sharesFor(100, 2).hard < P.sharesFor(100, 5).hard && P.sharesFor(100, 5).hard < P.sharesFor(100, 10).hard);
check("no class means the board year", JSON.stringify(P.sharesFor(70)) === JSON.stringify(P.sharesFor(70, 10)));
check("class bands accept '10', 'Class 10' and numbers", P.classBand("Class 10") === "9-10" && P.classBand("4") === "3-5" && P.classBand(1) === "1-2" && P.classBand(undefined) === "9-10");

// ── Whole percentages ────────────────────────────────────────────────────
{
  let ok = true;
  let detail = "";
  for (const band of BANDS) {
    for (let level = 0; level <= 100; level += 1) {
      const m = P.mixPercents(level, band);
      const sum = m.easy + m.medium + m.hard;
      const exact = P.sharesFor(level, band);
      const drift = Math.max(Math.abs(m.easy - exact.easy * 100), Math.abs(m.medium - exact.medium * 100), Math.abs(m.hard - exact.hard * 100));
      if (sum !== 100 || drift >= 1 || !Number.isInteger(m.easy)) {
        ok = false;
        detail = `band ${band} level ${level}: ${JSON.stringify(m)}`;
      }
    }
  }
  check("the shown percentages are whole numbers that add up to exactly 100", ok, detail);
}

// ── Words ────────────────────────────────────────────────────────────────
check(
  "the readout has a word for every part of the slider, in order",
  [0, 20, 50, 75, 100].map(P.describeLevel).join() === "Gentle,Easier,Balanced,Harder,Demanding",
);
check("every level explains itself", [0, 50, 100].every((n) => P.explainLevel(n).length > 20));

// ── The slider's markup ──────────────────────────────────────────────────
{
  const html = renderToStaticMarkup(createElement(DifficultySlider, { value: 70, onChange() {}, classNum: 10 }));
  const mix = P.mixPercents(70, 10);
  check("it is a native range input from 0 to 100", /type="range"/.test(html) && /min="0"/.test(html) && /max="100"/.test(html));
  check("it shows the current level", /value="70"/.test(html));
  check("it names the level in words", html.includes("Harder"));
  check("it announces the mix to assistive technology", html.includes(`about ${mix.easy}% basic, ${mix.medium}% moderate and ${mix.hard}% challenging`));
  check("it draws the mix as a bar of the right widths", html.includes(`width:${mix.easy}%`) && html.includes(`width:${mix.hard}%`));
  check("it labels the control", /<label[^>]*for="difficulty-slider"[^>]*>Difficulty<\/label>/.test(html));
  const young = renderToStaticMarkup(createElement(DifficultySlider, { value: 100, onChange() {}, classNum: 2 }));
  const board = renderToStaticMarkup(createElement(DifficultySlider, { value: 100, onChange() {}, classNum: 10 }));
  check("the preview follows the class", young !== board && young.includes(`${P.mixPercents(100, 2).hard}%`));
  const clamped = renderToStaticMarkup(createElement(DifficultySlider, { value: 999, onChange() {} }));
  check("an out-of-range value is clamped, not trusted", /value="100"/.test(clamped));
}

if (failures) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log("\nAll difficulty-slider checks passed");
