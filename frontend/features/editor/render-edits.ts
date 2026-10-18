/**
 * Drawing a list of edits onto a copy of a picture, and getting pictures in and
 * out of the browser.
 *
 * Everything here is a deterministic canvas operation: a highlight is a
 * translucent rectangle, a cover is a white one, a label is text. Nothing
 * repaints the picture's own content, so a diagram's numbers and labels cannot
 * change by accident. The upload is never modified; `renderEditedImage` works on
 * a fresh canvas.
 */

import { cropRect, outputSize, type ImageEdit, type RectEdit } from "./image-edits";

/** What the server accepts, and a size that keeps the model's reading sharp. */
export const MAX_UPLOAD_BYTES = 8 * 1024 * 1024;
const SAFE_UPLOAD_BYTES = 6 * 1024 * 1024;
const SAFE_SIDE = 4000;
const MODEL_SIDE = 2400;

export const ACCEPTED_TYPES = ["image/png", "image/jpeg", "image/webp", "image/gif"] as const;

function hexToRgba(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

/** Load a file (or Blob) as an image element, ready to draw. */
export function loadImage(source: Blob | string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = typeof source === "string" ? source : URL.createObjectURL(source);
    const img = new Image();
    img.onload = () => {
      if (typeof source !== "string") URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      if (typeof source !== "string") URL.revokeObjectURL(url);
      reject(new Error("That file could not be opened as an image."));
    };
    img.src = url;
  });
}

function toBlob(canvas: HTMLCanvasElement, type: string, quality?: number): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("The picture could not be encoded."))), type, quality),
  );
}

/**
 * Draw `edits` over `img` on a new canvas and return it.
 *
 * Annotations are placed on the full image; a crop, if any, then selects the
 * window that becomes the output; the result is scaled down to `maxSide`.
 */
export function renderEditedImage(
  img: CanvasImageSource & { naturalWidth?: number; naturalHeight?: number; width: number; height: number },
  edits: readonly ImageEdit[],
  maxSide = MODEL_SIDE,
): HTMLCanvasElement {
  const nw = img.naturalWidth || img.width;
  const nh = img.naturalHeight || img.height;

  // 1. The full picture with every annotation on it.
  const full = document.createElement("canvas");
  full.width = nw;
  full.height = nh;
  const ctx = full.getContext("2d")!;
  ctx.drawImage(img, 0, 0, nw, nh);

  const unitPx = Math.min(nw, nh);
  const stroke = Math.max(2, unitPx * 0.006);

  for (const edit of edits) {
    if (edit.op === "crop") continue;
    if (edit.op === "highlight") {
      const r = edit as RectEdit;
      ctx.fillStyle = hexToRgba(r.color || "#ffd400", 0.38);
      ctx.fillRect(r.x * nw, r.y * nh, r.w * nw, r.h * nh);
    } else if (edit.op === "box") {
      const r = edit as RectEdit;
      ctx.strokeStyle = r.color || "#e11d48";
      ctx.lineWidth = stroke;
      ctx.strokeRect(r.x * nw, r.y * nh, r.w * nw, r.h * nh);
    } else if (edit.op === "cover") {
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(edit.x * nw, edit.y * nh, edit.w * nw, edit.h * nh);
    } else if (edit.op === "arrow") {
      const x1 = edit.x1 * nw;
      const y1 = edit.y1 * nh;
      const x2 = edit.x2 * nw;
      const y2 = edit.y2 * nh;
      const angle = Math.atan2(y2 - y1, x2 - x1);
      const head = Math.max(10, unitPx * 0.03);
      ctx.strokeStyle = edit.color || "#e11d48";
      ctx.fillStyle = edit.color || "#e11d48";
      ctx.lineWidth = stroke;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(x1, y1);
      ctx.lineTo(x2 - Math.cos(angle) * head * 0.6, y2 - Math.sin(angle) * head * 0.6);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(x2, y2);
      ctx.lineTo(x2 - head * Math.cos(angle - Math.PI / 7), y2 - head * Math.sin(angle - Math.PI / 7));
      ctx.lineTo(x2 - head * Math.cos(angle + Math.PI / 7), y2 - head * Math.sin(angle + Math.PI / 7));
      ctx.closePath();
      ctx.fill();
    } else if (edit.op === "label") {
      const size = Math.max(14, Math.round(unitPx * 0.045));
      ctx.font = `600 ${size}px Arial, Helvetica, sans-serif`;
      ctx.textBaseline = "top";
      // A white halo keeps the text legible over whatever it lands on.
      ctx.lineJoin = "round";
      ctx.lineWidth = Math.max(3, size * 0.28);
      ctx.strokeStyle = "#ffffff";
      ctx.strokeText(edit.text, edit.x * nw, edit.y * nh);
      ctx.fillStyle = edit.color || "#111827";
      ctx.fillText(edit.text, edit.x * nw, edit.y * nh);
    }
  }

  // 2. The crop window (or everything), at the output size.
  const crop = cropRect(edits);
  const { width, height } = outputSize(nw, nh, edits, maxSide);
  const out = document.createElement("canvas");
  out.width = width;
  out.height = height;
  const octx = out.getContext("2d")!;
  octx.imageSmoothingQuality = "high";
  if (crop) {
    octx.drawImage(full, crop.x * nw, crop.y * nh, crop.w * nw, crop.h * nh, 0, 0, width, height);
  } else {
    octx.drawImage(full, 0, 0, width, height);
  }
  return out;
}

/** The edited picture as a PNG blob (lossless, so labels and lines stay sharp). */
export async function renderEditedBlob(img: HTMLImageElement, edits: readonly ImageEdit[]): Promise<Blob> {
  return toBlob(renderEditedImage(img, edits), "image/png");
}

/**
 * Get a chosen file ready to upload, and say whether it had to be shrunk.
 *
 * A picture inside the server's limits goes up byte for byte, which is what
 * "preserve the original" means. Only one too big for the server is re-encoded
 * smaller, so a phone photo still works.
 */
export async function prepareUpload(file: File): Promise<{ blob: Blob; resized: boolean; width: number; height: number }> {
  const img = await loadImage(file);
  const width = img.naturalWidth;
  const height = img.naturalHeight;
  const fits = file.size <= SAFE_UPLOAD_BYTES && Math.max(width, height) <= SAFE_SIDE;
  if (fits) return { blob: file, resized: false, width, height };

  const scale = Math.min(1, SAFE_SIDE / Math.max(width, height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  canvas.getContext("2d")!.drawImage(img, 0, 0, canvas.width, canvas.height);
  const blob = await toBlob(canvas, "image/jpeg", 0.9);
  return { blob, resized: true, width: canvas.width, height: canvas.height };
}
