import jsPDF from "jspdf";
import html2canvas from "html2canvas";

// ---------------------------------------------------------------------------
// Tailwind v4 / shadcn use oklch() color functions everywhere.
// html2canvas only understands rgb/hex, so we override every CSS custom
// property with its plain-hex equivalent inside the cloned document.
// ---------------------------------------------------------------------------
const OKLCH_OVERRIDES = `
  :root, .dark, * {
    --background:                 #ffffff !important;
    --foreground:                 #09090b !important;
    --card:                       #ffffff !important;
    --card-foreground:            #09090b !important;
    --popover:                    #ffffff !important;
    --popover-foreground:         #09090b !important;
    --primary:                    #18181b !important;
    --primary-foreground:         #fafafa !important;
    --secondary:                  #f4f4f5 !important;
    --secondary-foreground:       #18181b !important;
    --muted:                      #f4f4f5 !important;
    --muted-foreground:           #71717a !important;
    --accent:                     #f4f4f5 !important;
    --accent-foreground:          #18181b !important;
    --destructive:                #dc2626 !important;
    --border:                     #e4e4e7 !important;
    --input:                      #e4e4e7 !important;
    --ring:                       #a1a1aa !important;
    --sidebar:                    #fafafa !important;
    --sidebar-foreground:         #09090b !important;
    --sidebar-primary:            #18181b !important;
    --sidebar-primary-foreground: #fafafa !important;
    --sidebar-accent:             #f4f4f5 !important;
    --sidebar-accent-foreground:  #18181b !important;
    --sidebar-border:             #e4e4e7 !important;
    --sidebar-ring:               #a1a1aa !important;
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

/** Patch a cloned document so html2canvas can parse all CSS colours. */
function patchClonedDocument(clonedDoc: Document): void {
  // 1. Inject CSS-variable overrides (highest priority)
  const override = clonedDoc.createElement("style");
  override.textContent = OKLCH_OVERRIDES;
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
  ".logo-remove-btn",
  ".drawing-delete",
  ".float-image-hide-in-pdf", // alignment toolbar + resize handle
];

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
): Promise<void> {
  const container = document.getElementById(elementId);
  if (!container) throw new Error(`Element #${elementId} not found`);

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

  /** html2canvas options shared across all page captures. */
  const captureOptions: Parameters<typeof html2canvas>[1] = {
    scale: 2,
    useCORS: true,
    logging: false,
    backgroundColor: "#ffffff",
    onclone: (clonedDoc: Document) => {
      patchClonedDocument(clonedDoc);
      HIDE_IN_PDF.forEach((sel) => {
        clonedDoc
          .querySelectorAll<HTMLElement>(sel)
          .forEach((el) => (el.style.display = "none"));
      });
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

      const imgData = canvas.toDataURL("image/png");

      // How tall would this image be if we stretched it to fill the PDF width?
      const naturalH = pdfW * (canvas.height / canvas.width); // mm

      if (naturalH <= pdfH) {
        // ✅ Fits on one page — centre vertically
        const yOff = (pdfH - naturalH) / 2;
        pdf.addImage(imgData, "PNG", 0, yOff, pdfW, naturalH);
      } else {
        // ⚠️ Taller than A4 (content overflow) — scale down proportionally
        // so everything is visible on one page.  No floating-point slice loops.
        const scaleFactor = pdfH / naturalH;
        const scaledW = pdfW * scaleFactor;
        const xOff = (pdfW - scaledW) / 2;
        pdf.addImage(imgData, "PNG", xOff, 0, scaledW, pdfH);
      }
    }

    if (!pdfHasContent) {
      throw new Error("Nothing to export — no pages were captured.");
    }

    pdf.save(filename);
  } catch (error) {
    console.error("Error exporting PDF:", error);
    // Re-throw so the caller (toolbar) can show the error toast.
    throw error instanceof Error ? error : new Error("Failed to export PDF");
  }
}
