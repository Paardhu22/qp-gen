#!/usr/bin/env node
// Guards the institute logo on the paper header, end to end through the parts
// that have no other test.
//
// The coupling this exists for: `header-node.tsx` renders the logo, and BOTH
// export paths read that rendered markup back out — `export-pdf.ts` inlines
// every `<img>` before rasterising, and `export-docx.ts` looks specifically
// for `.paper-header-logo`, `data-logo-url` and `data-logo-width` to size an
// ImageRun. None of those selectors is checked by a type, so renaming a class
// in the renderer would print a logo on screen and silently drop it from every
// file the teacher actually sends out.
//
// And the logo-fitting rules (`masthead.ts`): logos come in every shape, so
// each is sized by height, capped in width, and a wordmark goes on top.
//
// Also re-checks the ProseMirror content-hole rule for this node, which
// test-todom-shape.mjs does not cover.
//
// Run from frontend/: `node scripts/test-header-logo.mjs`

import { fileURLToPath } from "node:url";
import path from "node:path";
import { createJiti } from "jiti";

const here = path.dirname(fileURLToPath(import.meta.url));
const jiti = createJiti(here, {
  interopDefault: true,
  jsx: true,
  extensions: [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"],
  alias: { "@": path.resolve(here, "..") },
  transformOptions: { babel: { plugins: [] } },
});

const { PaperHeaderBlock } = await jiti.import(
  path.resolve(here, "../components/editor/extensions/header-node.tsx"),
);
const { fitLogo, resolveLogoSide } = await jiti.import(
  path.resolve(here, "../components/editor/masthead.ts"),
);

if (!PaperHeaderBlock?.config?.renderHTML) {
  throw new Error("PaperHeaderBlock has no renderHTML — import failed?");
}

let failures = 0;
function check(label, condition, detail = "") {
  if (condition) {
    console.log(`PASS  ${label}`);
  } else {
    failures += 1;
    console.error(`FAIL  ${label}${detail ? ` — ${detail}` : ""}`);
  }
}

function render(attrs) {
  return PaperHeaderBlock.config.renderHTML.call(
    { type: { name: "paperHeaderBlock" } },
    { HTMLAttributes: attrs },
  );
}

/** Depth-first search for the first array whose tag name matches. */
function findTag(spec, tag) {
  if (!Array.isArray(spec)) return null;
  if (spec[0] === tag) return spec;
  for (const child of spec) {
    const found = findTag(child, tag);
    if (found) return found;
  }
  return null;
}

function attrsOf(spec) {
  return spec && typeof spec[1] === "object" && !Array.isArray(spec[1])
    ? spec[1]
    : {};
}

/** The ProseMirror rule: a content hole must be its parent's only child. */
function validateHole(spec, at = "$") {
  if (!Array.isArray(spec)) return;
  let start = 1;
  if (
    spec.length > 1 &&
    spec[1] !== null &&
    typeof spec[1] === "object" &&
    !Array.isArray(spec[1])
  ) {
    start = 2;
  }
  const children = spec.slice(start);
  const holeIdx = children.indexOf(0);
  if (holeIdx !== -1 && children.length > 1) {
    throw new Error(
      `Content hole rule violated at ${at}: parent has ${children.length} children`,
    );
  }
  for (let i = start; i < spec.length; i++) validateHole(spec[i], `${at}[${i}]`);
}

// ── No logo: nothing is emitted, and the node still renders ────────────────
{
  const spec = render({ showDate: false, dateValue: "", logoUrl: "" });
  check("no logo → no <img> in the spec", findTag(spec, "img") === null);
  let holeOk = true;
  try {
    validateHole(spec);
  } catch (e) {
    holeOk = false;
    console.error(`      ${e.message}`);
  }
  check("no logo → content hole rule holds", holeOk);
}

// ── With a logo: the markup both exporters depend on ───────────────────────
{
  const spec = render({
    showDate: false,
    dateValue: "",
    logoUrl: "/media/brand-assets/u1/crest.png",
    logoHeight: 88,
    logoAlign: "left",
  });

  const img = findTag(spec, "img");
  check("logo → an <img> is emitted", img !== null);

  const imgAttrs = attrsOf(img);
  check(
    "logo <img> carries the .paper-header-logo class export-docx selects on",
    imgAttrs.class === "paper-header-logo",
    `got class="${imgAttrs.class}"`,
  );
  check(
    "logo <img> src is resolved, not left as a bare relative path",
    typeof imgAttrs.src === "string" &&
      imgAttrs.src.endsWith("/media/brand-assets/u1/crest.png"),
    `got src="${imgAttrs.src}"`,
  );
  check(
    "logo <img> height cap comes from the attribute",
    String(imgAttrs.style || "").includes("max-height:88px"),
    `got style="${imgAttrs.style}"`,
  );

  const root = attrsOf(spec);
  check(
    "root carries data-logo-url for the DOCX fallback lookup",
    root["data-logo-url"] === "/media/brand-assets/u1/crest.png",
  );
  check(
    "root carries data-logo-height for the DOCX size calculation",
    root["data-logo-height"] === "88",
  );
  check("root carries data-logo-align", root["data-logo-align"] === "left");

  let holeOk = true;
  try {
    validateHole(spec);
  } catch (e) {
    holeOk = false;
    console.error(`      ${e.message}`);
  }
  check("logo → content hole rule still holds", holeOk);
}

// ── Placement is a float side, read from the wrapper ───────────────────────
{
  const sideOf = (align) => {
    const spec = render({ logoUrl: "/media/x.png", logoHeight: 64, logoAlign: align });
    // spec[2] is the shell; its children are the logo, the content, the date.
    const wrap = spec[2].slice(2).find(
      (child) => Array.isArray(child) && attrsOf(child).class === "paper-header-logo-wrap",
    );
    return attrsOf(wrap)["data-side"];
  };
  check("logoAlign=left → data-side=left", sideOf("left") === "left");
  check("logoAlign=right → data-side=right", sideOf("right") === "right");
  check("logoAlign=top → data-side=top", sideOf("top") === "top");
  check("logoAlign=auto with no shape known → left", sideOf("auto") === "left");
}

// ── Fitting: every shape reads at the same weight ──────────────────────────
{
  const crest = fitLogo(1, 64, "left");
  check("a square crest prints at the chosen height", crest.width === 64 && crest.height === 64);

  const emblem = fitLogo(0.5, 64, "left");
  check("a tall emblem keeps its height, not its width", emblem.height === 64 && emblem.width === 32);

  const wordmark = fitLogo(4, 64, "left");
  check(
    "a wordmark beside the title is capped in width, keeping its shape",
    wordmark.width === 170 && wordmark.height === Math.round(170 / 4),
    JSON.stringify(wordmark),
  );
  const onTop = fitLogo(4, 64, "top");
  check("a wordmark on top gets the wider cap", onTop.width === 256 && onTop.height === 64);

  check("auto puts a wordmark on top", resolveLogoSide("auto", 3.5) === "top");
  check("auto keeps a crest at the side", resolveLogoSide("auto", 1.1) === "left");
  check("an explicit side wins over the shape", resolveLogoSide("right", 4) === "right");
}

// ── parseHTML round-trips what renderHTML wrote ────────────────────────────
{
  const rule = PaperHeaderBlock.config.parseHTML.call({})[0];
  const fakeEl = {
    _attrs: {
      "data-show-date": "true",
      "data-date-value": "2026-08-03",
      "data-logo-url": "/media/crest.png",
      "data-logo-height": "48",
      "data-logo-align": "top",
    },
    getAttribute(name) {
      return this._attrs[name] ?? null;
    },
  };
  const parsed = rule.getAttrs(fakeEl);
  check("parse recovers logoUrl", parsed.logoUrl === "/media/crest.png");
  check("parse recovers logoHeight as a number", parsed.logoHeight === 48);
  check("parse recovers logoAlign", parsed.logoAlign === "top");

  // A document written before logos existed must still open.
  const legacyEl = {
    getAttribute(name) {
      return name === "data-show-date" ? "false" : null;
    },
  };
  const legacy = rule.getAttrs(legacyEl);
  check("a pre-logo document parses with no logo", legacy.logoUrl === "");
  check(
    "a pre-logo document gets the default height, not NaN",
    legacy.logoHeight === 64,
    `got ${legacy.logoHeight}`,
  );
  check("a pre-logo document defaults to auto placement", legacy.logoAlign === "auto");
  check("existing headers keep the school name visible", legacy.showSchoolName === true);
  const hiddenSchool = attrsOf(render({ showSchoolName: false }));
  check("school visibility survives saved HTML", rule.getAttrs({ getAttribute: name => hiddenSchool[name] ?? null }).showSchoolName === false);
}

// Optional details survive saved HTML without printing hidden or blank values.
{
  const fields = [
    { id: "subject", label: "Subject", value: "Science & Technology" },
    { id: "set", label: "Set", value: "B" },
    { id: "time", label: "Time", value: "90 min" },
    { id: "marks", label: "Max marks", value: "" },
  ];
  const spec = render({ details: fields, hiddenFields: ["set", "time"] });
  validateHole(spec);
  const metadata = spec.find(child => Array.isArray(child) && child[0] === "div");
  const printed = JSON.stringify(metadata);
  check("hidden set and time are absent from printed header", !printed.includes('"Set:"') && !printed.includes('"Time:"'));
  check("blank values print no label", !printed.includes('"Max marks:"'));
  check("subject still prints", printed.includes("Science & Technology"));
  const rootAttrs = attrsOf(spec);
  const rule = PaperHeaderBlock.config.parseHTML.call({})[0];
  const roundTrip = rule.getAttrs({ getAttribute: name => rootAttrs[name] ?? null });
  check("hidden values are retained for re-enabling", roundTrip.details.find(field => field.id === "time").value === "90 min");
  check("visibility survives HTML round-trip", JSON.stringify(roundTrip.hiddenFields) === JSON.stringify(["set", "time"]));
  const empty = render({ details: fields, hiddenFields: fields.map(field => field.id), showDate: false });
  check("all hidden details leave no empty strip", !JSON.stringify(empty.slice(2)).includes("paper-header-details"));
}

// New papers use supplied information rather than fixed sample values.
{
  const { headerJSONFromBrand, clearBrandHeaderCache } = await jiti.import(path.resolve(here, "../lib/brand-header.ts"));
  clearBrandHeaderCache();
  check("new headers omit the generic subtitle", !headerJSONFromBrand().content.some(node => node.type === "heading" && node.attrs.level === 2));
  check("generic exam metadata cannot reinsert the subtitle", !headerJSONFromBrand({ examName: "CBSE - Question Paper" }).content.some(node => node.type === "heading" && node.attrs.level === 2));
  const header = headerJSONFromBrand({ subject: "Mathematics", className: "8", marks: 75, examName: "Unit Assessment" });
  const fields = header.attrs.details;
  check("new headers have no details grid", !header.content.some(node => node.type === "table"));
  check("new headers use actual subject, class and marks", fields.find(f => f.id === "subject").value === "Mathematics" && fields.find(f => f.id === "class").value === "8" && fields.find(f => f.id === "marks").value === "75");
  check("set and time stay blank until supplied", fields.find(f => f.id === "set").value === "" && fields.find(f => f.id === "time").value === "");
  check("exam title remains separate from school details", header.content[1].content[0].text === "Unit Assessment");
  header.attrs.details[0].value = "Changed";
  check("one paper cannot change another header's defaults", headerJSONFromBrand().attrs.details.every(f => f.value === ""));
}

console.log(
  failures === 0
    ? "\nAll header-logo cases passed"
    : `\n${failures} case(s) FAILED`,
);
process.exit(failures === 0 ? 0 : 1);
