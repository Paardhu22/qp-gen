/**
 * Download the paper in the editor as a Word document.
 *
 * The layout lives in `docx-paper.ts`, built from the editor's document; this
 * file is the browser half — fetching every image the paper prints, in a form
 * Word can embed, and saving the file.
 */

import { Packer } from "docx";
import { saveAs } from "file-saver";

import { resolveFigureSrc } from "@/components/editor/extensions/float-image";
import { buildPaperDocx, type LoadedImage } from "./docx-paper";

/** Formats Word embeds as they are; anything else (SVG, WebP) becomes a PNG. */
const NATIVE: Record<string, LoadedImage["type"]> = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/jpg": "jpg",
  "image/gif": "gif",
  "image/bmp": "bmp",
};

/** Long edge a vector is drawn at, so it stays sharp at print resolution. */
const RASTER_EDGE = 1600;

function decode(blob: Blob): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve(img);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("image failed to decode"));
    };
    img.src = url;
  });
}

async function toPng(img: HTMLImageElement, vector: boolean): Promise<Uint8Array> {
  const scale = vector ? Math.min(4, RASTER_EDGE / Math.max(img.naturalWidth, img.naturalHeight)) : 1;
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(img.naturalWidth * Math.max(scale, 1)));
  canvas.height = Math.max(1, Math.round(img.naturalHeight * Math.max(scale, 1)));
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas unavailable");
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
  if (!blob) throw new Error("canvas produced no image");
  return new Uint8Array(await blob.arrayBuffer());
}

/**
 * One image as Word needs it, or null — a figure that will not load is left
 * out rather than failing the whole export.
 */
async function loadImage(rawSrc: string): Promise<LoadedImage | null> {
  const src = resolveFigureSrc(rawSrc);
  if (!src) return null;
  try {
    // `fetch` reads data: URLs as well as /media/ ones. "same-origin"
    // credentials: media needs no cookie, and a split-origin deploy rejects
    // credentialed requests without an explicit allow header.
    const response = await fetch(src, { mode: "cors", credentials: "same-origin" });
    if (!response.ok) return null;
    const blob = await response.blob();
    const img = await decode(blob);
    const native = NATIVE[blob.type.toLowerCase()];
    return {
      data: native ? new Uint8Array(await blob.arrayBuffer()) : await toPng(img, blob.type.includes("svg")),
      type: native ?? "png",
      width: img.naturalWidth,
      height: img.naturalHeight,
    };
  } catch {
    return null;
  }
}

/** `source` is the editor's root element (TipTap hangs the editor on it). */
export async function exportToDocx(
  source: HTMLElement,
  filename = "exam-paper.docx",
): Promise<Blob> {
  const editor = (source as HTMLElement & { editor?: { getJSON(): any } }).editor;
  if (!editor) throw new Error("No editor to export.");
  const document = await buildPaperDocx(editor.getJSON(), loadImage);
  const blob = await Packer.toBlob(document);
  saveAs(blob, filename);
  return blob;
}
