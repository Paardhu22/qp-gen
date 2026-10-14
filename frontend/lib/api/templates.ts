/** Blueprints and paper templates: the catalogue, resolving, saving, folders and question-type menu. */
"use client";

import { fetchJson } from "@/lib/api/http";

/** Where one question slot's content comes from. */
export type SlotSource = "generate" | "saved";

/** One question position, as the Blueprint Builder edits it. */
export interface BlueprintSlot {
  index: number;
  sectionTitle: string;
  /** The runtime shape ("MCQ"). */
  questionType: string;
  /** The catalogue type the teacher picked ("MCQ_ODD_ONE_OUT"). */
  typeCode?: string;
  /** Ask for higher-order thinking (Bloom Analyze and above). */
  hots?: boolean;
  /** Frame the question in a real-world situation. */
  competency?: boolean;
  marks: number;
  source: SlotSource;
  choiceRequired: boolean;
  /** Engine fields the Builder does not show. Round-trip untouched. */
  passthrough?: Record<string, unknown>;
}

/**
 * Totals arrive computed from the slots — the backend never echoes back a
 * total the client sent. Treat them as read-only: to change a total, change
 * the slots.
 */
export interface Blueprint {
  slots: BlueprintSlot[];
  totalQuestions: number;
  totalMarks: number;
  generatedCount: number;
  savedCount: number;
  byType: Record<string, number>;
  bySection: { title: string; questions: number; marks: number }[];
}

export const EMPTY_BLUEPRINT: Blueprint = {
  slots: [],
  totalQuestions: 0,
  totalMarks: 0,
  generatedCount: 0,
  savedCount: 0,
  byType: {},
  bySection: [],
};

/** A built-in starting point. Generated server-side; never a stored row. */
export interface BuiltinTemplate {
  id: string;
  name: string;
  description: string;
  /** "starter": a ready blueprint for a class band, built from the catalogue. */
  kind: "cbse_blueprint" | "blank" | "instructions" | "starter";
  builtin: true;
  board: string;
  academicClass: string;
  subject: string;
  settings: Record<string, string>;
  /** The classes a starter suits, inclusive. Absent on every other kind. */
  classRange?: [number, number];
  /** The paper's total, on starters and board cards. */
  totalMarks?: number;
}

export interface PaperTemplate {
  id: string;
  name: string;
  instructions: string;
  settings: Record<string, string>;
  blueprint: Blueprint;
  /** True when the teacher edited slots, so the stored blueprint is authoritative. */
  pinned: boolean;
  builtin: false;
  base_template_id: string;
  source_config: Record<string, unknown>;
  /** Which folder this is filed in; null means unfiled, a normal resting state. */
  folderId: string | null;
  last_used_at: string | null;
  created_at: string;
  updated_at: string;
}

/** Anything the picker can show. Switch on `builtin` to tell them apart. */
export type PickableTemplate = BuiltinTemplate | PaperTemplate;

export interface QuestionTypeOption {
  /** The catalogue type ("MCQ_ODD_ONE_OUT") — written to a slot as typeCode. */
  code: string;
  /** Its runtime shape ("MCQ") — written to a slot as questionType. */
  shape: string;
  label: string;
  /** The family it is filed under, e.g. "Objective — Choice Based". */
  group: string;
  family: string;
  defaultMarks: number;
  marksRange: [number, number];
  classes: [number, number];
  /** "needs_picture" types are listed but cannot be chosen. */
  availability: "available" | "needs_picture";
  /** Why an unavailable type cannot be chosen; empty when it can. */
  reason: string;
  /** What the type measures, in a line. */
  tests: string;
  example: string;
  /** Whether the class this menu was fetched for is usually set this type. */
  inClass: boolean;
  /** How often the menu's subject sets this type. */
  weight: "core" | "occasional" | "rare";
  /** Core for this subject, set in this class, and printable: the picker opens on these. */
  common: boolean;
}

/** Built-ins and the teacher's own, in one call — the picker shows one grid. */
export async function fetchTemplateCatalog(params?: {
  subject?: string;
  academicClass?: string;
}): Promise<{ templates: PaperTemplate[]; builtin: BuiltinTemplate[] }> {
  const query = new URLSearchParams();
  if (params?.subject) query.set("subject", params.subject);
  if (params?.academicClass) query.set("class", params.academicClass);
  const suffix = query.toString() ? `?${query}` : "";
  const data = await fetchJson<{
    templates: PaperTemplate[];
    builtin: BuiltinTemplate[];
  }>(`/api/generation/templates${suffix}`, { method: "GET" });
  return { templates: data.templates ?? [], builtin: data.builtin ?? [] };
}

/**
 * Compile a template into an editable blueprint. Writes nothing, so browsing
 * the picker never commits the teacher to anything.
 */
/**
 * Settings the resolve read off the template itself — out of a plain-English
 * brief, or off the board card that was picked. Only the keys it actually
 * settled are present, because the Builder writes these over a form the
 * teacher may already have touched: absent means "leave their setting alone",
 * which a null or an empty string could not say.
 */
export interface DetectedSettings {
  subject?: string;
  academicClass?: string;
  totalMarks?: number;
  numberOfSets?: string;
  difficulty?: string;
}

export interface ResolvedTemplate {
  blueprint: Blueprint;
  template?: PaperTemplate;
  detected?: DetectedSettings;
  /** What the designer had to change, e.g. a stated total the slots miss. */
  corrections?: string[];
}

export async function resolveTemplate(body: {
  templateId: string;
  subject?: string;
  academicClass?: string;
  difficulty?: string;
  instructions?: string;
  savedCount?: number;
}): Promise<ResolvedTemplate> {
  return fetchJson<ResolvedTemplate>("/api/generation/templates/resolve", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * The per-slot type menu for the Blueprint Builder. Served so the
 * subject-appropriate mapping can change server-side.
 *
 * Distinct from `fetchQuestionTypes` above, which returns the `QuestionType`
 * DB vocabulary used for classifying saved questions. Same words, different
 * jobs: this one is a menu a teacher picks from.
 */
export async function fetchQuestionTypeMenu(
  subject?: string,
  /**
   * The generator that owns the slot being re-typed.
   *
   * Sent by the editor's "change type" menu and omitted by the Blueprint
   * Builder, and the difference matters: the Builder edits slots that have not
   * been routed yet, while the editor is changing a slot whose generator is
   * already fixed. `slot_accepts` gates on provenance before type, so a type
   * that generator cannot write is a choice that always fails.
   */
  generator?: string,
  /** The class the paper is for, so the menu can suggest that class's types. */
  academicClass?: string | number,
): Promise<QuestionTypeOption[]> {
  const query = new URLSearchParams();
  if (subject) query.set("subject", subject);
  if (generator) query.set("generator", generator);
  if (academicClass) query.set("class", String(academicClass));
  const suffix = query.toString() ? `?${query}` : "";
  const data = await fetchJson<{ questionTypes: QuestionTypeOption[] }>(
    `/api/generation/question-types${suffix}`,
    { method: "GET" },
  );
  return data.questionTypes ?? [];
}

// ── On-demand question images ──────────────────────────────────────────────

export async function fetchPaperTemplates(): Promise<PaperTemplate[]> {
  const data = await fetchJson<{ templates: PaperTemplate[] }>(
    "/api/generation/templates",
    { method: "GET" },
  );
  return data.templates ?? [];
}

/**
 * Save, or overwrite the template of the same name.
 *
 * Either `instructions` or `blueprint` is required — a teacher who edited
 * slots should not also have to write prose describing what they did.
 */
export async function savePaperTemplate(body: {
  name: string;
  instructions?: string;
  settings?: Record<string, string>;
  blueprint?: { slots: BlueprintSlot[] };
  baseTemplateId?: string;
  sourceConfig?: Record<string, unknown>;
  folderId?: string | null;
}): Promise<PaperTemplate> {
  const data = await fetchJson<{ template: PaperTemplate }>(
    "/api/generation/templates",
    { method: "POST", body: JSON.stringify(body) },
  );
  return data.template;
}

/** Fetch a template's contents and mark it as used (drives picker ordering). */
export async function applyPaperTemplate(
  templateId: string,
): Promise<PaperTemplate> {
  const data = await fetchJson<{ template: PaperTemplate }>(
    `/api/generation/templates/${templateId}`,
    { method: "POST", body: JSON.stringify({}) },
  );
  return data.template;
}

export async function deletePaperTemplate(templateId: string): Promise<void> {
  await fetchJson<void>(`/api/generation/templates/${templateId}`, {
    method: "DELETE",
  });
}

/**
 * Edit a saved template in place.
 *
 * Distinct from `savePaperTemplate`, which is create-or-overwrite-by-name, and
 * from `applyPaperTemplate`, which only records that a template was used. Only
 * the keys present in `body` are touched server-side, so a rename cannot blank
 * a blueprint — pass exactly what is changing.
 *
 * `folderId: null` unfiles; `blueprint: null` reverts a pinned template to
 * instruction-driven.
 */
export async function updatePaperTemplate(
  templateId: string,
  body: {
    name?: string;
    instructions?: string;
    settings?: Record<string, string>;
    blueprint?: { slots: BlueprintSlot[] } | null;
    sourceConfig?: Record<string, unknown>;
    folderId?: string | null;
  },
): Promise<PaperTemplate> {
  const data = await fetchJson<{ template: PaperTemplate }>(
    `/api/generation/templates/${templateId}`,
    { method: "PATCH", body: JSON.stringify(body) },
  );
  return data.template;
}

/**
 * Turn a built-in catalog entry into a row the teacher owns.
 *
 * Built-ins are generated server-side from the engine's eligibility matrix —
 * code, not rows — which is what keeps the picker in step with the engine but
 * also means a built-in has nothing to edit and nowhere to be filed. Forking
 * resolves it once and writes it down; from then on it is an ordinary template.
 */
export async function forkBuiltinTemplate(body: {
  templateId: string;
  name?: string;
  subject?: string;
  academicClass?: string;
  instructions?: string;
  folderId?: string | null;
}): Promise<PaperTemplate> {
  const data = await fetchJson<{ template: PaperTemplate }>(
    "/api/generation/templates/fork",
    { method: "POST", body: JSON.stringify(body) },
  );
  return data.template;
}

/** Copy one of your own templates. The copy starts unused. */
export async function duplicatePaperTemplate(
  templateId: string,
  body: { name?: string; folderId?: string | null } = {},
): Promise<PaperTemplate> {
  const data = await fetchJson<{ template: PaperTemplate }>(
    `/api/generation/templates/${templateId}/duplicate`,
    { method: "POST", body: JSON.stringify(body) },
  );
  return data.template;
}

// ── Template folders ───────────────────────────────────────────────────────
//
// Purely the teacher's filing: nothing in generation reads a folder, and an
// unfiled template is completely usable. See backend `TemplateFolder`.

export interface TemplateFolder {
  id: string;
  name: string;
  /** Null for a root folder. */
  parentId: string | null;
  /** Templates filed directly here — not counting subfolders. */
  templateCount: number;
  created_at: string;
  updated_at: string;
}

export async function fetchTemplateFolders(): Promise<TemplateFolder[]> {
  const data = await fetchJson<{ folders: TemplateFolder[] }>(
    "/api/generation/template-folders",
    { method: "GET" },
  );
  return data.folders ?? [];
}

export async function createTemplateFolder(body: {
  name: string;
  parentId?: string | null;
}): Promise<TemplateFolder> {
  const data = await fetchJson<{ folder: TemplateFolder }>(
    "/api/generation/template-folders",
    { method: "POST", body: JSON.stringify(body) },
  );
  return data.folder;
}

/** Rename (`name`) or re-file (`parentId`, null for root) one folder. */
export async function updateTemplateFolder(
  folderId: string,
  body: { name?: string; parentId?: string | null },
): Promise<TemplateFolder> {
  const data = await fetchJson<{ folder: TemplateFolder }>(
    `/api/generation/template-folders/${folderId}`,
    { method: "PATCH", body: JSON.stringify(body) },
  );
  return data.folder;
}

/**
 * Delete a folder. Its subfolders go with it; the templates inside do not —
 * they fall back to unfiled. Tidying up filing must never destroy a recipe.
 */
export async function deleteTemplateFolder(folderId: string): Promise<void> {
  await fetchJson<void>(`/api/generation/template-folders/${folderId}`, {
    method: "DELETE",
  });
}

// ── Brand kit ──────────────────────────────────────────────────────────────
//
// A school's identity, stored once and applied to every paper instead of being
// retyped into each header. See backend `services/brand_kit.py`.
