#!/usr/bin/env node
// How an export fetches an image — run from frontend/:  node scripts/test-export-media.mjs
//
// The institute's logo and every figure were silently missing from exported
// PDFs because /media/<path> redirects to a presigned S3 URL, and after a
// cross-origin redirect the browser asks S3 with `Origin: null`, which a bucket
// CORS rule naming the app's origin does not answer. The exporters now ask the
// backend for the bytes (`?inline=1`) and fall back to the plain URL.

import { fileURLToPath } from "node:url";
import path from "node:path";
import { createJiti } from "jiti";

const here = path.dirname(fileURLToPath(import.meta.url));
const jiti = createJiti(here, { interopDefault: true });
const { inlineMediaUrl, fetchImageBlob, resetImageFailures, takeImageFailures } = await jiti.import(
  path.resolve(here, "../features/export/fetch-image.ts"),
);

let failures = 0;
function check(label, condition, detail = "") {
  if (condition) console.log(`PASS  ${label}`);
  else {
    failures += 1;
    console.error(`FAIL  ${label}${detail ? ` — ${detail}` : ""}`);
  }
}

// ── Which URLs are asked for as bytes ───────────────────────────────────
const API = "https://api.hsatedu.in";
check("an API /media/ URL asks for the bytes", inlineMediaUrl(`${API}/media/brand/logo.png`) === `${API}/media/brand/logo.png?inline=1`);
check("a relative /media/ URL does too", inlineMediaUrl("/media/brand/logo.png") === "/media/brand/logo.png?inline=1");
check("an existing query string is extended, not replaced", inlineMediaUrl(`${API}/media/a.png?v=2`) === `${API}/media/a.png?v=2&inline=1`);
check("asking twice does not double the parameter", inlineMediaUrl(inlineMediaUrl("/media/a.png")) === "/media/a.png?inline=1");
check("a presigned URL is left alone (a parameter would void the signature)", inlineMediaUrl("https://b.s3.amazonaws.com/media/a.png?X-Amz-Signature=abc") === "https://b.s3.amazonaws.com/media/a.png?X-Amz-Signature=abc");
check("data: and blob: URLs are left alone", inlineMediaUrl("data:image/png;base64,AAAA") === "data:image/png;base64,AAAA" && inlineMediaUrl("blob:https://x/1") === "blob:https://x/1");
check("a URL that is not /media/ is left alone", inlineMediaUrl("https://example.com/pic.png") === "https://example.com/pic.png" && inlineMediaUrl("/static/pic.png") === "/static/pic.png");
check("empty stays empty", inlineMediaUrl("") === "");

// ── Fetching, with a stubbed fetch ──────────────────────────────────────
const realFetch = globalThis.fetch;
const realWarn = console.warn;
let calls = [];
let warnings = [];
console.warn = (...args) => warnings.push(args.join(" "));
const png = new Blob([new Uint8Array([137, 80, 78, 71])], { type: "image/png" });
const ok = () => ({ ok: true, blob: async () => png });
const fail = (status) => ({ ok: false, status, blob: async () => new Blob([]) });

async function run(url, respond) {
  calls = [];
  warnings = [];
  resetImageFailures();
  globalThis.fetch = async (u, init) => {
    calls.push({ url: u, init });
    return respond(u, calls.length);
  };
  return fetchImageBlob(url);
}

try {
  let blob = await run("/media/brand/logo.png", () => ok());
  check("the backend's bytes are used when it streams them", blob === png && calls.length === 1 && calls[0].url === "/media/brand/logo.png?inline=1");
  check("the request is CORS-mode with no cookies", calls[0].init.mode === "cors" && calls[0].init.credentials === "same-origin");

  blob = await run("/media/brand/logo.png", (u) => (u.includes("inline=1") ? fail(404) : ok()));
  check("a 404 on the inline form falls back to the plain URL", blob === png && calls.length === 2 && calls[1].url === "/media/brand/logo.png");

  blob = await run("/media/brand/logo.png", (u) => {
    if (u.includes("inline=1")) throw new TypeError("Failed to fetch");
    return ok();
  });
  check("a network error on the inline form falls back too (an older backend)", blob === png && calls.length === 2);

  blob = await run("/media/brand/logo.png", () => {
    throw new TypeError("Failed to fetch");
  });
  check("an image that cannot be read at all is null", blob === null && calls.length === 2);
  check("…is recorded as a failure, once", takeImageFailures().length === 1 && takeImageFailures()[0] === "/media/brand/logo.png");
  check("…and warned about in the console", warnings.length === 1 && warnings[0].includes("/media/brand/logo.png"));

  blob = await run("data:image/png;base64,AAAA", () => ok());
  check("a data: URL is fetched once, as it is", blob === png && calls.length === 1 && calls[0].url === "data:image/png;base64,AAAA");

  blob = await run("https://b.s3.amazonaws.com/x.png?X-Amz-Signature=s", () => ok());
  check("a presigned URL is fetched once, unmodified", calls.length === 1 && calls[0].url.endsWith("X-Amz-Signature=s"));

  // The same image failing twice (the header and a repeat) is one failure.
  resetImageFailures();
  globalThis.fetch = async () => {
    throw new TypeError("x");
  };
  await fetchImageBlob("/media/a.png");
  await fetchImageBlob("/media/a.png");
  await fetchImageBlob("/media/b.png");
  check("failures are distinct by URL", takeImageFailures().length === 2);
  resetImageFailures();
  check("reset forgets them", takeImageFailures().length === 0);
} finally {
  globalThis.fetch = realFetch;
  console.warn = realWarn;
}

if (failures) {
  console.error(`\n${failures} check(s) failed`);
  process.exit(1);
}
console.log("\nAll export-media checks passed");
