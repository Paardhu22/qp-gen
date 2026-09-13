/**
 * Question type lookups for the editor, backed by the generated catalogue.
 *
 * A question block carries two type fields. `questionType` is the runtime
 * shape the editor lays out (MCQ, SHORT_ANSWER, CASE_STUDY), which every stored
 * document already has. `typeCode` is the catalogue type the teacher chose
 * (MCQ_ODD_ONE_OUT), present on questions generated since the catalogue. These
 * helpers take either, so no caller has to know which one a document holds.
 */

import {
  QUESTION_TYPES,
  SHAPE_DEFAULT_TYPE,
  SHAPE_LABELS,
  type QuestionTypeInfo,
} from "@/lib/question-types.generated";

const normalize = (raw: unknown) =>
  String(raw ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

/** The catalogue entry for a type code or a runtime shape, if either is known. */
export function questionTypeInfo(raw: unknown): QuestionTypeInfo | undefined {
  const key = normalize(raw);
  if (!key) return undefined;
  return QUESTION_TYPES[key] ?? QUESTION_TYPES[SHAPE_DEFAULT_TYPE[key] ?? ""];
}

/**
 * How a teacher reads a question's type.
 *
 * A type that is simply its shape's default reads under the shape's plain name
 * — "Multiple Choice", not "MCQ — Standard" — so a paper full of ordinary
 * questions stays quiet, and only a chosen variant ("MCQ — Odd One Out") shows
 * its precise label. Undefined when nothing is known, so a caller can fall back
 * to its own wording.
 */
export function questionTypeLabel(
  typeCode: unknown,
  shape?: unknown,
): string | undefined {
  const info = QUESTION_TYPES[normalize(typeCode)];
  if (info) {
    return SHAPE_DEFAULT_TYPE[info.shape] === info.code
      ? SHAPE_LABELS[info.shape] ?? info.label
      : info.label;
  }
  const shapeKey = normalize(shape) || normalize(typeCode);
  return SHAPE_LABELS[shapeKey] ?? questionTypeInfo(shapeKey)?.label;
}

/** True when the type is laid out as a head block plus a run of paragraphs. */
export function isCompositeType(typeCode: unknown, shape?: unknown): boolean {
  return Boolean(
    questionTypeInfo(typeCode)?.composite || questionTypeInfo(shape)?.composite,
  );
}
