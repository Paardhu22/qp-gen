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
    logoWidth: 104,
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
    "logo <img> width comes from the attribute",
    String(imgAttrs.style || "").includes("width:104px"),
    `got style="${imgAttrs.style}"`,
  );

  const root = attrsOf(spec);
  check(
    "root carries data-logo-url for the DOCX fallback lookup",
    root["data-logo-url"] === "/media/brand-assets/u1/crest.png",
  );
  check(
    "root carries data-logo-width for the DOCX size calculation",
    root["data-logo-width"] === "104",
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

// ── Alignment changes the order, not just a class ──────────────────────────
{
  const layoutChildren = (align) => {
    const spec = render({
      logoUrl: "/media/x.png",
      logoWidth: 72,
      logoAlign: align,
    });
    // The layout row is the root div's only child; its children are the
    // image and the text column, in whichever order alignment dictates.
    return spec[2].slice(2);
  };

  const left = layoutChildren("left");
  const right = layoutChildren("right");
  check(
    "logoAlign=left puts the image before the text column",
    Array.isArray(left[0]) && left[0][0] === "img",
    `first child was ${Array.isArray(left[0]) ? left[0][0] : typeof left[0]}`,
  );
  check(
    "logoAlign=right puts the image after the text column",
    Array.isArray(right[right.length - 1]) &&
      right[right.length - 1][0] === "img",
    `last child was ${
      Array.isArray(right[right.length - 1])
        ? right[right.length - 1][0]
        : typeof right[right.length - 1]
    }`,
  );
}

// ── parseHTML round-trips what renderHTML wrote ────────────────────────────
{
  const rule = PaperHeaderBlock.config.parseHTML.call({})[0];
  const fakeEl = {
    _attrs: {
      "data-show-date": "true",
      "data-date-value": "2026-08-03",
      "data-logo-url": "/media/crest.png",
      "data-logo-width": "48",
      "data-logo-align": "right",
    },
    getAttribute(name) {
      return this._attrs[name] ?? null;
    },
  };
  const parsed = rule.getAttrs(fakeEl);
  check("parse recovers logoUrl", parsed.logoUrl === "/media/crest.png");
  check("parse recovers logoWidth as a number", parsed.logoWidth === 48);
  check("parse recovers logoAlign", parsed.logoAlign === "right");

  // A document written before logos existed must still open.
  const legacyEl = {
    getAttribute(name) {
      return name === "data-show-date" ? "false" : null;
    },
  };
  const legacy = rule.getAttrs(legacyEl);
  check("a pre-logo document parses with no logo", legacy.logoUrl === "");
  check(
    "a pre-logo document gets the default width, not NaN",
    legacy.logoWidth === 72,
    `got ${legacy.logoWidth}`,
  );
  check(
    "a pre-logo document defaults to left alignment",
    legacy.logoAlign === "left",
  );
}

console.log(
  failures === 0
    ? "\nAll header-logo cases passed"
    : `\n${failures} case(s) FAILED`,
);
process.exit(failures === 0 ? 0 : 1);
