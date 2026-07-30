import jsPDF from "jspdf";
import html2canvas from "html2canvas";
import { resolveFigureSrc } from "@/components/editor/extensions/float-image";

// ---------------------------------------------------------------------------
// Tailwind v4 / shadcn use oklch() color functions everywhere.
// html2canvas only understands rgb/hex, so we override every CSS custom
// property with its plain-hex equivalent inside the cloned document.
//
// These are the LIGHT theme's tokens flattened to hex — an export is always a
// white page, whatever theme the app is in. Kept in step with the theme kit in
// `app/globals.css` (ink #282d3c, sand #D7C3A3): if they drift, chrome that
// leaks into a PDF is tinted with the previous palette.
// ---------------------------------------------------------------------------
const OKLCH_OVERRIDES = `
  :root, .dark, * {
    --background:                 #ffffff !important;
    --foreground:                 #09090b !important;
    --card:                       #ffffff !important;
    --card-foreground:            #09090b !important;
    --popover:                    #ffffff !important;
    --popover-foreground:         #09090b !important;
    --primary:                    #282d3c !important;
    --primary-foreground:         #ffffff !important;
    --secondary:                  #f7f2ea !important;
    --secondary-foreground:       #282d3c !important;
    --muted:                      #f7f2ea !important;
    --muted-foreground:           #6b6f7a !important;
    --accent:                     #efe4d2 !important;
    --accent-foreground:          #282d3c !important;
    --destructive:                #dc2626 !important;
    --border:                     #e5e0d6 !important;
    --input:                      #e5e0d6 !important;
    --ring:                       #282d3c !important;
    --sidebar:                    #fafafa !important;
    --sidebar-foreground:         #09090b !important;
    --sidebar-primary:            #282d3c !important;
    --sidebar-primary-foreground: #ffffff !important;
    --sidebar-accent:             #efe4d2 !important;
    --sidebar-accent-foreground:  #282d3c !important;
    --sidebar-border:             #e5e0d6 !important;
    --sidebar-ring:               #282d3c !important;
  }
`;

// Known oklch values → hex (Tailwind v4 zinc + destructive palette)
const OKLCH_TO_HEX: Record<string, string> = {
  "oklch(1 0 0)": "#ffffff",
  "oklch(0.985 0 0)": "#fafafa",
  "oklch(0.97 0 0)": "#f4f4f5",
  "oklch(0.922 0 0)": "#e4e4e7",
  "oklch(0.708 0 0)": "#a1a1aa",
  "oklch(0.556 0 0)": "#71717a",
  "oklch(0.439 0 0)": "#52525b",
  "oklch(0.371 0 0)": "#3f3f46",
  "oklch(0.269 0 0)": "#27272a",
  "oklch(0.205 0 0)": "#18181b",
  "oklch(0.145 0 0)": "#09090b",
  "oklch(0.577 0.245 27.325)": "#dc2626",
  "oklch(0.704 0.191 22.216)": "#ef4444",
  "oklch(0.488 0.243 264.376)": "#6366f1",
  "oklch(1 0 0 / 10%)": "rgba(255,255,255,0.10)",
  "oklch(1 0 0 / 15%)": "rgba(255,255,255,0.15)",
};

/**
 * Screen chrome that must never reach the PDF.
 *
 * html2canvas renders SCREEN styles, not print styles — so the page's on-screen
 * border and drop shadow would be rasterised into the exported document as a
 * grey outline and a smudge along every page edge. The `@media print` rules in
 * editor.css already strip them, but that media query never applies here.
 *
 * The canvas tint behind the sheets is not listed: it sits on the scroll
 * container, which is an ancestor of the capture root rather than part of it,
 * so it never reaches the clone in the first place.
 */
const PAGE_CHROME_RESET = `
  .doc-page {
    border: none !important;
    box-shadow: none !important;
    background: #ffffff !important;
  }
`;

/** Patch a cloned document so html2canvas can parse all CSS colours. */
function patchClonedDocument(clonedDoc: Document): void {
  // 1. Inject CSS-variable overrides (highest priority)
  const override = clonedDoc.createElement("style");
  override.textContent = OKLCH_OVERRIDES + PAGE_CHROME_RESET;
  clonedDoc.head.insertBefore(override, clonedDoc.head.firstChild);

  // 2. Text-replace oklch / lab / lch in every existing <style> block
  clonedDoc.querySelectorAll("style").forEach((styleEl) => {
    if (styleEl === override) return;
    let css = styleEl.textContent ?? "";
    for (const [from, to] of Object.entries(OKLCH_TO_HEX)) {
      css = css.split(from).join(to);
    }
    // Generic fallback for any remaining modern color functions
    css = css.replace(/oklch\s*\([^)]*\)/g, "#000");
    css = css.replace(/\blab\s*\([^)]*\)/g, "#000");
    css = css.replace(/\blch\s*\([^)]*\)/g, "#000");
    css = css.replace(/\boklab\s*\([^)]*\)/g, "#000");
    styleEl.textContent = css;
  });

  // 3. Sanitize inline style attributes (html2canvas reads these directly)
  clonedDoc.querySelectorAll<HTMLElement>("*").forEach((el) => {
    const styleAttr = el.getAttribute("style");
    if (!styleAttr) return;

    let next = styleAttr;
    for (const [from, to] of Object.entries(OKLCH_TO_HEX)) {
      next = next.split(from).join(to);
    }
    next = next.replace(/oklch\s*\([^)]*\)/g, "#000");
    next = next.replace(/\blab\s*\([^)]*\)/g, "#000");
    next = next.replace(/\blch\s*\([^)]*\)/g, "#000");
    next = next.replace(/\boklab\s*\([^)]*\)/g, "#000");

    if (next !== styleAttr) el.setAttribute("style", next);
  });
}

/** CSS selectors for editor UI chrome that should not appear in the PDF. */
const HIDE_IN_PDF = [
  ".question-controls",
  ".section-controls",
  ".instruction-controls",
  ".question-group-controls",
  ".paper-header-delete",
  ".paper-header-actions",
  ".logo-remove-btn",
  ".drawing-delete",
  ".float-image-hide-in-pdf", // alignment toolbar + resize handle
];

// Issue 1 — paper header date: replace the `<input type="date">` (an editor
// affordance) with a formatted, human-readable text span when exporting. The
// editor shows only the input so the user never sees a duplicate date; PDF
// readers need a printable date string, not a date-picker widget rendering.
function rewriteHeaderDateForExport(clonedDoc: Document): void {
  const rows = clonedDoc.querySelectorAll<HTMLElement>(
    ".paper-header-date-row",
  );
  rows.forEach((row) => {
    const input = row.querySelector<HTMLInputElement>(
      "input.paper-header-date-input",
    );
    const iso =
      row.getAttribute("data-date-value") ||
      input?.getAttribute("value") ||
      input?.value ||
      "";
    if (input) input.remove();

    if (!iso) return;
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return;
    let pretty: string;
    try {
      pretty = new Intl.DateTimeFormat(undefined, {
        day: "2-digit",
        month: "short",
        year: "numeric",
      }).format(d);
    } catch {
      pretty = d.toDateString();
    }
    const span = clonedDoc.createElement("span");
    span.className = "paper-header-date-display";
    span.textContent = " " + pretty;
    row.appendChild(span);
  });
}

// ---------------------------------------------------------------------------
// Figure pre-processing
//
// html2canvas can't read pixels from a cross-origin <img> unless the server
// returned `Access-Control-Allow-Origin` AND the img was loaded with
// `crossorigin="anonymous"`. In our deployment topology the editor and the
// Django media origin frequently differ (Next on :3000 vs Django on :8000,
// or the FE on https://app.x and media on https://api.x), so html2canvas
// would silently render a blank box for every `/media/...` figure.
//
// Pre-resolving every `<img>` to an inline `data:` URL sidesteps the CORS
// dance entirely: html2canvas reads from local memory, not the network. It
// also keeps PDF output deterministic — failed fetches are detected here
// rather than producing a half-rendered raster page later.
// ---------------------------------------------------------------------------

async function blobToDataUrl(blob: Blob): Promise<string> {
  return await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("FileReader failed"));
    reader.readAsDataURL(blob);
  });
}

async function fetchAsDataUrl(url: string): Promise<string | null> {
  try {
    // cors mode plus credentials: same-origin lets Django's session cookie
    // through for first-party deployments without leaking it cross-site.
    const response = await fetch(url, {
      mode: "cors",
      credentials: "same-origin",
    });
    if (!response.ok) return null;
    const blob = await response.blob();
    return await blobToDataUrl(blob);
  } catch {
    return null;
  }
}

/**
 * Walk every `<img>` in `root` and replace its `src` with an inline data URL.
 * Returns the count of substitutions performed; callers can log this to spot
 * silent fetch failures during export.
 */
async function inlineAllImageSources(root: HTMLElement): Promise<number> {
  const imgs = Array.from(root.querySelectorAll<HTMLImageElement>("img"));
  // Dedupe identical URLs so we don't refetch repeated figures.
  const fetchCache = new Map<string, Promise<string | null>>();

  const jobs = imgs.map(async (img) => {
    const original = img.getAttribute("src") || "";
    if (!original) return false;
    if (original.startsWith("data:")) return true; // already inline

    const resolved = resolveFigureSrc(original);
    if (!resolved) return false;
    if (resolved.startsWith("data:")) {
      img.setAttribute("src", resolved);
      return true;
    }

    let job = fetchCache.get(resolved);
    if (!job) {
      job = fetchAsDataUrl(resolved);
      fetchCache.set(resolved, job);
    }
    const dataUrl = await job;
    if (!dataUrl) return false;
    img.setAttribute("src", dataUrl);
    // crossOrigin attribute is no longer meaningful for a data: URL; remove
    // it so html2canvas doesn't re-trigger a CORS dance.
    img.removeAttribute("crossorigin");
    return true;
  });

  const results = await Promise.all(jobs);
  return results.filter(Boolean).length;
}

// ---------------------------------------------------------------------------
// KaTeX / inline-SVG pre-rasterization
//
// html2canvas cannot reliably draw inline `<svg>` elements — and KaTeX
// draws radical signs (√), wide accents, and stretchy delimiters as inline
// SVG paths. The visible symptom (s3b paper, Q38 & several MCQ options):
// "√5" exports as just "5" — the digits are HTML text spans and survive,
// the radical is an SVG and is silently dropped.
//
// html2canvas DOES render `<img>` elements faithfully (it decodes the
// source through the browser's own image pipeline — the same property the
// figure pipeline above relies on). So: in the cloned document, replace
// every laid-out inline `<svg>` with an `<img>` whose src is the
// serialized SVG as a data URL, pinned to the box the SVG occupied.
// Overflow-cropping wrappers (KaTeX `.hide-tail`) keep working because the
// replacement occupies the exact same box and the wrapper still clips.
// ---------------------------------------------------------------------------

function inlineSvgElementsAsImages(root: HTMLElement): number {
  const svgs = Array.from(root.querySelectorAll("svg"));
  let converted = 0;
  for (const svg of svgs) {
    const rect = svg.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) continue; // hidden — skip
    const view = svg.ownerDocument.defaultView;
    const computed = view ? view.getComputedStyle(svg) : null;

    const clone = svg.cloneNode(true) as SVGElement;
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    // Pin intrinsic dimensions: an SVG-in-<img> without width/height can
    // fall back to 300×150 and distort.
    clone.setAttribute("width", String(rect.width));
    clone.setAttribute("height", String(rect.height));
    // KaTeX paths carry no fill and inherit currentColor from the math
    // span; an <img> cannot inherit CSS colour, so bake it in.
    if (!clone.getAttribute("fill")) {
      clone.setAttribute("fill", computed?.color || "#000000");
    }

    const xml = new XMLSerializer().serializeToString(clone);
    const img = svg.ownerDocument.createElement("img");
    img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(xml)}`;
    img.style.width = `${rect.width}px`;
    img.style.height = `${rect.height}px`;
    if (computed) {
      img.style.display = computed.display === "inline" ? "inline-block" : computed.display;
      img.style.verticalAlign = computed.verticalAlign;
    }
    svg.replaceWith(img);
    converted += 1;
  }
  return converted;
}

// ---------------------------------------------------------------------------
// Main export function
// ---------------------------------------------------------------------------

/**
 * Captures each A4 page in the Tiptap editor and assembles a PDF.
 *
 * Rendering is entirely client-side (html2canvas + jsPDF) — no server / API
 * calls are made.
 *
 * Each `.doc-page` element (794 × 1123 px ≈ A4 at 96 DPI) is captured
 * individually at 2× resolution and placed on its own PDF page.  If a page
 * somehow overflows A4 proportions it is scaled down to fit rather than
 * sliced, which avoids the floating-point edge cases that plagued earlier
 * implementations.
 */
export async function exportToPDF(
  elementId: string,
  filename = "exam-paper.pdf",
): Promise<Blob> {
  const container = document.getElementById(elementId);
  if (!container) throw new Error(`Element #${elementId} not found`);

  // KaTeX layout depends on the KaTeX webfonts. If a capture races font
  // loading, html2canvas measures with fallback fonts and stacked layouts
  // (fractions, superscripts) come out misaligned. Fonts are cached after
  // first paint, so this normally resolves instantly.
  await document.fonts.ready;

  // Collect individual page elements; fall back to the whole container.
  const pageEls = Array.from(
    container.querySelectorAll<HTMLElement>(".doc-page"),
  );
  const targets: HTMLElement[] = pageEls.length > 0 ? pageEls : [container];

  const pdf = new jsPDF({
    orientation: "portrait",
    unit: "mm",
    format: "a4",
  });
  const pdfW = pdf.internal.pageSize.getWidth(); // 210 mm
  const pdfH = pdf.internal.pageSize.getHeight(); // 297 mm

  /** html2canvas options shared across all page captures.
   *
   * `scale: 2` keeps text crisp at A4. `useCORS` stays on as a belt-and-
   * braces fallback for any image we somehow missed pre-inlining (e.g. a
   * background-image added by a future feature).
   *
   * The heavy lifting on figures happens in `onclone` via
   * `inlineAllImageSources` — by the time html2canvas serializes pixels,
   * every `<img>` already points at a `data:` URL, so the canvas can never
   * be tainted by a cross-origin figure.
   */
  const captureOptions: Parameters<typeof html2canvas>[1] = {
    scale: 2,
    useCORS: true,
    logging: false,
    backgroundColor: "#ffffff",
    onclone: async (clonedDoc: Document) => {
      patchClonedDocument(clonedDoc);
      HIDE_IN_PDF.forEach((sel) => {
        clonedDoc
          .querySelectorAll<HTMLElement>(sel)
          .forEach((el) => (el.style.display = "none"));
      });
      rewriteHeaderDateForExport(clonedDoc);
      await inlineAllImageSources(clonedDoc.body);
      // After image inlining (so we never convert an SVG we're about to
      // replace anyway): swap inline SVGs (KaTeX radicals, accents,
      // drawing nodes) for data-URL <img>s that html2canvas can draw.
      inlineSvgElementsAsImages(clonedDoc.body);
    },
  };

  try {
    let pdfHasContent = false;

    for (let i = 0; i < targets.length; i++) {
      const canvas = await html2canvas(targets[i], captureOptions);

      // Skip degenerate captures (shouldn't happen, but guard anyway)
      if (canvas.width === 0 || canvas.height === 0) continue;

      if (pdfHasContent) pdf.addPage();
      pdfHasContent = true;

      // JPEG at quality 0.92 keeps text + linework crisp while cutting page
      // bytes 5–10× vs PNG. Exam papers have small flat-colour regions
      // (white space, black text, simple figures) that PNG's lossless
      // encoder can't compress as aggressively as JPEG's DCT. The savings
      // are what take a 30-page paper from ~90 MB → ~3 MB.
      const imgData = canvas.toDataURL("image/jpeg", 0.92);

      // How tall would this image be if we stretched it to fill the PDF width?
      const naturalH = pdfW * (canvas.height / canvas.width); // mm

      if (naturalH <= pdfH) {
        // ✅ Fits on one page — centre vertically
        const yOff = (pdfH - naturalH) / 2;
        pdf.addImage(imgData, "JPEG", 0, yOff, pdfW, naturalH, undefined, "FAST");
      } else {
        // ⚠️ Taller than A4 (content overflow) — scale down proportionally
        // so everything is visible on one page.  No floating-point slice loops.
        const scaleFactor = pdfH / naturalH;
        const scaledW = pdfW * scaleFactor;
        const xOff = (pdfW - scaledW) / 2;
        pdf.addImage(imgData, "JPEG", xOff, 0, scaledW, pdfH, undefined, "FAST");
      }
    }

    if (!pdfHasContent) {
      throw new Error("Nothing to export — no pages were captured.");
    }

    pdf.save(filename);
    return pdf.output("blob") as Blob;
  } catch (error) {
    console.error("Error exporting PDF:", error);
    // Re-throw so the caller (toolbar) can show the error toast.
    throw error instanceof Error ? error : new Error("Failed to export PDF");
  }
}
