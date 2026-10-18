/**
 * Edits to a teacher's picture: what they are, and the geometry of drawing them.
 *
 * An edit is a small instruction applied to a COPY of the image — never to the
 * upload. All coordinates are fractions (0–1) of the ORIGINAL image's width and
 * height, from the top-left. Annotations are drawn on the full image and a crop,
 * if there is one, is applied last, so moving a crop never moves a label.
 *
 * `sanitizeEdits` mirrors `services/generation/image_question.sanitize_edits`
 * on the backend and is the one gate edits pass through, whether the teacher
 * drew them or the AI proposed them. Everything else here is pure geometry — no
 * DOM, no canvas — so it can be checked in Node; drawing lives in
 * `render-edits.ts`.
 */

export type RectOp = "crop" | "highlight" | "box" | "cover";
export type EditOp = RectOp | "arrow" | "label";

export interface RectEdit {
  op: RectOp;
  x: number;
  y: number;
  w: number;
  h: number;
  color?: string;
}
export interface ArrowEdit {
  op: "arrow";
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  color?: string;
}
export interface LabelEdit {
  op: "label";
  x: number;
  y: number;
  text: string;
  color?: string;
}
export type ImageEdit = RectEdit | ArrowEdit | LabelEdit;

export const EDIT_OPS: readonly EditOp[] = ["crop", "highlight", "box", "arrow", "label", "cover"];
export const MAX_EDITS = 30;
export const MAX_LABEL_CHARS = 60;
/** A box smaller than this (a fraction of the picture) is a stray click. */
export const MIN_BOX = 0.005;

export const DEFAULT_COLOURS: Record<string, string> = {
  highlight: "#ffd400",
  box: "#e11d48",
  arrow: "#e11d48",
  label: "#111827",
};
const COLOUR = /^#[0-9a-fA-F]{6}$/;

export const clamp01 = (n: number): number => Math.max(0, Math.min(1, n));
const round4 = (n: number): number => Math.round(n * 10000) / 10000;

export function isRect(edit: ImageEdit): edit is RectEdit {
  return edit.op === "crop" || edit.op === "highlight" || edit.op === "box" || edit.op === "cover";
}

function unit(value: unknown): number | null {
  const n = typeof value === "string" && value.trim() !== "" ? Number(value) : value;
  if (typeof n !== "number" || !Number.isFinite(n)) return null;
  return clamp01(n);
}

function colourFor(op: EditOp, raw: unknown): string | undefined {
  if (!(op in DEFAULT_COLOURS)) return undefined;
  return typeof raw === "string" && COLOUR.test(raw) ? raw : DEFAULT_COLOURS[op];
}

/** The valid edits in `raw`, clamped to the picture. Never throws. */
export function sanitizeEdits(raw: unknown): ImageEdit[] {
  if (!Array.isArray(raw)) return [];
  const edits: ImageEdit[] = [];
  for (const item of raw) {
    if (edits.length >= MAX_EDITS) break;
    if (!item || typeof item !== "object") continue;
    const e = item as Record<string, unknown>;
    const op = e.op as EditOp;
    if (!EDIT_OPS.includes(op)) continue;

    if (op === "crop" || op === "highlight" || op === "box" || op === "cover") {
      const x = unit(e.x);
      const y = unit(e.y);
      let w = unit(e.w);
      let h = unit(e.h);
      if (x === null || y === null || w === null || h === null) continue;
      w = Math.min(w, 1 - x);
      h = Math.min(h, 1 - y);
      if (w < MIN_BOX || h < MIN_BOX) continue;
      const edit: RectEdit = { op, x: round4(x), y: round4(y), w: round4(w), h: round4(h) };
      const color = colourFor(op, e.color);
      if (color) edit.color = color;
      edits.push(edit);
    } else if (op === "arrow") {
      const [x1, y1, x2, y2] = ["x1", "y1", "x2", "y2"].map((k) => unit(e[k]));
      if (x1 === null || y1 === null || x2 === null || y2 === null) continue;
      if (Math.abs(x1 - x2) < MIN_BOX && Math.abs(y1 - y2) < MIN_BOX) continue;
      edits.push({
        op,
        x1: round4(x1),
        y1: round4(y1),
        x2: round4(x2),
        y2: round4(y2),
        color: colourFor(op, e.color),
      });
    } else {
      const x = unit(e.x);
      const y = unit(e.y);
      const text = String(e.text ?? "").split(/\s+/).filter(Boolean).join(" ").slice(0, MAX_LABEL_CHARS);
      if (x === null || y === null || !text) continue;
      edits.push({ op, x: round4(x), y: round4(y), text, color: colourFor(op, e.color) });
    }
  }
  // One crop: the last one wins.
  const lastCrop = edits.map((e) => e.op).lastIndexOf("crop");
  return edits.filter((e, i) => e.op !== "crop" || i === lastCrop);
}

// ── Building a list of edits ────────────────────────────────────────────

/** The rectangle spanned by a drag, whichever corner it started from. */
export function rectFromDrag(x0: number, y0: number, x1: number, y1: number) {
  const x = clamp01(Math.min(x0, x1));
  const y = clamp01(Math.min(y0, y1));
  return { x, y, w: clamp01(Math.max(x0, x1)) - x, h: clamp01(Math.max(y0, y1)) - y };
}

/** `edits` with `edit` added: a new crop replaces the old one, and the list is capped. */
export function addEdit(edits: readonly ImageEdit[], edit: ImageEdit): ImageEdit[] {
  const kept = edit.op === "crop" ? edits.filter((e) => e.op !== "crop") : [...edits];
  if (kept.length >= MAX_EDITS) return kept;
  return sanitizeEdits([...kept, edit]);
}

export function removeEdit(edits: readonly ImageEdit[], index: number): ImageEdit[] {
  return edits.filter((_, i) => i !== index);
}

/** The crop rectangle, or null when the picture is not cropped. */
export function cropRect(edits: readonly ImageEdit[]): { x: number; y: number; w: number; h: number } | null {
  const crop = [...edits].reverse().find((e): e is RectEdit => e.op === "crop");
  return crop ? { x: crop.x, y: crop.y, w: crop.w, h: crop.h } : null;
}

/** The size of the edited picture: the crop's share of the original, shrunk to fit `maxSide`. */
export function outputSize(
  naturalWidth: number,
  naturalHeight: number,
  edits: readonly ImageEdit[],
  maxSide = 2400,
): { width: number; height: number } {
  const crop = cropRect(edits);
  const width = Math.max(1, Math.round(naturalWidth * (crop ? crop.w : 1)));
  const height = Math.max(1, Math.round(naturalHeight * (crop ? crop.h : 1)));
  const scale = Math.min(1, maxSide / Math.max(width, height));
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

/** Whether applying `edits` would change a single pixel. */
export function changesPicture(edits: readonly ImageEdit[]): boolean {
  return edits.length > 0;
}

// ── Moving and resizing ────────────────────────────────────────────────

/** `edit` shifted by (dx, dy), kept wholly inside the picture. */
export function moveEdit(edit: ImageEdit, dx: number, dy: number): ImageEdit {
  if (isRect(edit)) {
    return {
      ...edit,
      x: round4(clamp01(Math.min(edit.x + dx, 1 - edit.w))),
      y: round4(clamp01(Math.min(edit.y + dy, 1 - edit.h))),
    };
  }
  if (edit.op === "arrow") {
    const sx = Math.max(-Math.min(edit.x1, edit.x2), Math.min(dx, 1 - Math.max(edit.x1, edit.x2)));
    const sy = Math.max(-Math.min(edit.y1, edit.y2), Math.min(dy, 1 - Math.max(edit.y1, edit.y2)));
    return { ...edit, x1: round4(edit.x1 + sx), y1: round4(edit.y1 + sy), x2: round4(edit.x2 + sx), y2: round4(edit.y2 + sy) };
  }
  return { ...edit, x: round4(clamp01(edit.x + dx)), y: round4(clamp01(edit.y + dy)) };
}

export type Handle = "nw" | "ne" | "sw" | "se" | "p1" | "p2";

/** Drag one handle of `edit` to (x, y); the opposite corner (or the other end) stays put. */
export function resizeEdit(edit: ImageEdit, handle: Handle, x: number, y: number): ImageEdit {
  const px = clamp01(x);
  const py = clamp01(y);
  if (isRect(edit)) {
    // The corner opposite the one being dragged does not move.
    const fixedX = handle === "nw" || handle === "sw" ? edit.x + edit.w : edit.x;
    const fixedY = handle === "nw" || handle === "ne" ? edit.y + edit.h : edit.y;
    const r = rectFromDrag(fixedX, fixedY, px, py);
    return { ...edit, x: round4(r.x), y: round4(r.y), w: round4(r.w), h: round4(r.h) };
  }
  if (edit.op === "arrow") {
    return handle === "p1" ? { ...edit, x1: round4(px), y1: round4(py) } : { ...edit, x2: round4(px), y2: round4(py) };
  }
  return edit;
}

/** The handles `edit` offers, with their positions. */
export function handlesOf(edit: ImageEdit): { handle: Handle; x: number; y: number }[] {
  if (isRect(edit)) {
    return [
      { handle: "nw", x: edit.x, y: edit.y },
      { handle: "ne", x: edit.x + edit.w, y: edit.y },
      { handle: "sw", x: edit.x, y: edit.y + edit.h },
      { handle: "se", x: edit.x + edit.w, y: edit.y + edit.h },
    ];
  }
  if (edit.op === "arrow") {
    return [
      { handle: "p1", x: edit.x1, y: edit.y1 },
      { handle: "p2", x: edit.x2, y: edit.y2 },
    ];
  }
  return [];
}

function distanceToSegment(px: number, py: number, x1: number, y1: number, x2: number, y2: number): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const lengthSq = dx * dx + dy * dy;
  const t = lengthSq === 0 ? 0 : Math.max(0, Math.min(1, ((px - x1) * dx + (py - y1) * dy) / lengthSq));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

/** The topmost edit under (x, y), or -1. Later edits sit on top of earlier ones. */
export function hitTest(edits: readonly ImageEdit[], x: number, y: number, tolerance = 0.015): number {
  for (let i = edits.length - 1; i >= 0; i -= 1) {
    const e = edits[i];
    if (isRect(e)) {
      if (x >= e.x - tolerance && x <= e.x + e.w + tolerance && y >= e.y - tolerance && y <= e.y + e.h + tolerance) return i;
    } else if (e.op === "arrow") {
      if (distanceToSegment(x, y, e.x1, e.y1, e.x2, e.y2) <= tolerance) return i;
    } else {
      const width = Math.max(0.04, e.text.length * 0.014);
      if (x >= e.x - tolerance && x <= e.x + width + tolerance && y >= e.y - tolerance && y <= e.y + 0.05 + tolerance) return i;
    }
  }
  return -1;
}

// ── Words ───────────────────────────────────────────────────────────────

function where(x: number, y: number): string {
  const vertical = y < 0.34 ? "upper" : y > 0.66 ? "lower" : "middle";
  const horizontal = x < 0.34 ? "left" : x > 0.66 ? "right" : "centre";
  if (vertical === "middle" && horizontal === "centre") return "centre";
  return `${vertical}-${horizontal}`;
}

export const EDIT_LABELS: Record<EditOp, string> = {
  crop: "Crop",
  highlight: "Highlight",
  box: "Box",
  arrow: "Arrow",
  label: "Label",
  cover: "Cover",
};

/** A short line for a list of edits: "Highlight · upper-left". */
export function describeEdit(edit: ImageEdit): string {
  if (isRect(edit)) return `${EDIT_LABELS[edit.op]} · ${where(edit.x + edit.w / 2, edit.y + edit.h / 2)}`;
  if (edit.op === "arrow") return `${EDIT_LABELS.arrow} · to ${where(edit.x2, edit.y2)}`;
  return `${EDIT_LABELS.label} “${edit.text}” · ${where(edit.x, edit.y)}`;
}
