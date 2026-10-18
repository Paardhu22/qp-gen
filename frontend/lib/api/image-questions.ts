/** Questions from a teacher's own image: write one, suggest edits to the picture, or store it. */
"use client";

import { fetchForm, fetchJson } from "@/lib/api/http";
import type { ImageEdit } from "@/features/editor/image-edits";

export interface ImageQuestionType {
  value: string;
  label: string;
}

/** What the AI made of the picture, shown so the teacher can see how it was read. */
export interface ImageUnderstanding {
  summary: string;
  kind: string;
  elements: string[];
  concerns: string[];
}

/** The picture as stored: the one to print, and the upload it came from, unchanged. */
export interface StoredImage {
  url: string;
  originalUrl: string;
  edited: boolean;
  edits: ImageEdit[];
  width: number;
  height: number;
  alt: string;
}

/** A generated question in the shape the editor inserts. */
export interface ImageQuestionWire {
  content: string;
  type: string;
  options: string[];
  answer: string;
  explanation?: string;
  marks: number;
  image_url: string;
  image_alt?: string;
  metadata: Record<string, unknown>;
}

export interface ImageQuestionResult {
  question: ImageQuestionWire;
  understanding: ImageUnderstanding;
  image: StoredImage;
  usedDescription: boolean;
  usedInstructions: boolean;
}

export interface ImageEditPlan {
  edits: ImageEdit[];
  notes: string[];
  unsupported: string[];
}

export interface ImageQuestionInput {
  /** What will be printed: the edited copy when `original` is given. */
  image: Blob;
  /** The upload as it arrived, sent only when `image` is an edited copy. */
  original?: Blob | null;
  edits?: ImageEdit[];
  description?: string;
  instructions?: string;
  subject?: string;
  classNum?: number | string;
  questionType?: string;
  marks?: number | null;
  difficulty?: string;
}

function pictureForm(input: { image: Blob; original?: Blob | null; edits?: ImageEdit[] }): FormData {
  const form = new FormData();
  form.append("image", input.image, "image");
  if (input.original && input.original !== input.image) form.append("original", input.original, "original");
  if (input.edits?.length) form.append("edits", JSON.stringify(input.edits));
  return form;
}

export function fetchImageQuestionTypes(): Promise<{ types: ImageQuestionType[] }> {
  return fetchJson<{ types: ImageQuestionType[] }>("/api/generation/image-question");
}

export function generateImageQuestion(input: ImageQuestionInput): Promise<ImageQuestionResult> {
  const form = pictureForm(input);
  const text = (key: string, value: unknown) => {
    const v = value === undefined || value === null ? "" : String(value).trim();
    if (v) form.append(key, v);
  };
  text("description", input.description);
  text("instructions", input.instructions);
  text("subject", input.subject);
  text("class", input.classNum);
  text("questionType", input.questionType);
  text("marks", input.marks);
  text("difficulty", input.difficulty);
  return fetchForm<ImageQuestionResult>("/api/generation/image-question", form);
}

export function planImageEdits(input: { image: Blob; instruction: string; description?: string }): Promise<ImageEditPlan> {
  const form = new FormData();
  form.append("image", input.image, "image");
  form.append("instruction", input.instruction);
  if (input.description?.trim()) form.append("description", input.description.trim());
  return fetchForm<ImageEditPlan>("/api/generation/image-edit-plan", form);
}

/** Store a picture for an existing question; no AI involved. */
export function uploadQuestionImage(input: {
  image: Blob;
  original?: Blob | null;
  edits?: ImageEdit[];
  description?: string;
}): Promise<StoredImage> {
  const form = pictureForm(input);
  if (input.description?.trim()) form.append("description", input.description.trim());
  return fetchForm<StoredImage>("/api/generation/image-upload", form);
}
