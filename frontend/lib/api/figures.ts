/** Per-question images and charts: image styles, figure specs and rendering. */
"use client";

import { fetchJson } from "@/lib/api/http";

export type QuestionImageStyle = "line_art" | "realistic" | "cartoon";

export interface QuestionImageStyleOption {
  value: QuestionImageStyle;
  label: string;
  description: string;
}

/** The style picker's options. Served so adding one needs no frontend release. */
export async function fetchQuestionImageStyles(): Promise<
  QuestionImageStyleOption[]
> {
  const data = await fetchJson<{ styles: QuestionImageStyleOption[] }>(
    "/api/generation/question-image",
    { method: "GET" },
  );
  return data.styles ?? [];
}

/**
 * Draw a figure for one question.
 *
 * Slow — image generation is tens of seconds — so the caller must show
 * progress. `timeoutMs` is raised well above the default for that reason: the
 * default would abort a request that was going to succeed.
 */
export async function generateQuestionImage(body: {
  questionText: string;
  style: QuestionImageStyle;
  imageDescription?: string;
}): Promise<{ imageUrl: string; style: QuestionImageStyle; cached: boolean }> {
  return fetchJson<{
    imageUrl: string;
    style: QuestionImageStyle;
    cached: boolean;
  }>("/api/generation/question-image", {
    method: "POST",
    body: JSON.stringify(body),
    timeoutMs: 180_000,
  });
}

/**
 * A chart the backend can draw exactly, read out of a question.
 *
 * This is the wire shape `services/figures/spec.py` validates, and it is what
 * the teacher edits in the dialog before anything is drawn — which is the
 * whole point of the two-step flow. A renderer fed the wrong numbers is still
 * wrong, and only the person who wrote the question can see that.
 */
export interface ChartDatum {
  label: string;
  value: number;
}

export interface ChartBin {
  lower: number;
  upper: number;
  value: number;
}

export interface ChartPoint {
  x: number;
  y: number;
  label: string;
}

export type ChartKind =
  | "pie"
  | "bar"
  | "histogram"
  | "line"
  | "number_line"
  | "coordinate_grid";

export interface ChartSpec {
  kind: "chart";
  chart: ChartKind;
  series?: ChartDatum[];
  bins?: ChartBin[];
  points?: ChartPoint[];
  xLabel: string;
  yLabel: string;
  /**
   * Whether the figure prints its own numbers. False whenever the question
   * asks the student to read or compute them — the figure must not answer the
   * question it illustrates.
   */
  showValues: boolean;
  yMax?: number;
  axisMin?: number;
  axisMax?: number;
  axisStep?: number;
}

export interface FigureSpecResult {
  kind: "chart" | "illustration";
  spec: ChartSpec | null;
}

/**
 * What figure does this question want, and with what numbers?
 *
 * Fast and cheap — a small structured model call — so the dialog can open on
 * it. Always resolves: anything it cannot read comes back as `illustration`,
 * which is the image-model path that already existed.
 */
export async function extractQuestionFigureSpec(body: {
  questionText: string;
}): Promise<FigureSpecResult> {
  return fetchJson<FigureSpecResult>("/api/generation/question-figure-spec", {
    method: "POST",
    body: JSON.stringify(body),
    timeoutMs: 60_000,
  });
}

/**
 * Draw a chart from a spec.
 *
 * No model, no spend, no waiting — this is arithmetic on the server, so the
 * default timeout is right and the dialog can call it on every edit.
 */
export async function renderQuestionFigure(body: {
  spec: ChartSpec;
}): Promise<{ imageUrl: string; kind: string; cached: boolean }> {
  return fetchJson<{ imageUrl: string; kind: string; cached: boolean }>(
    "/api/generation/question-figure",
    { method: "POST", body: JSON.stringify(body) },
  );
}
