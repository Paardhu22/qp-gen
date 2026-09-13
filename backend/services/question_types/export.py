"""Projections of the catalogue for the two places that cannot import it.

* **The database.** `QuestionType` and `QuestionFamily` rows are what
  `Question.type` points at, so they are seeded by a migration. A migration must
  be frozen — rerunning it next year has to do what it did today — so it reads
  a JSON snapshot of `db_snapshot()` taken when it was written, never the live
  catalogue.
* **The frontend.** `frontend/lib/question-types.generated.ts` carries the
  labels and layout traits the editor needs synchronously, without a request.

Both files are checked in, and `test_export.py` fails when either drifts from
the catalogue. `manage.py export_question_types` rewrites them.

Django-free, like the rest of the package.
"""

from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any, Dict, List

from services.question_types.families import FAMILIES
from services.question_types.registry import CATALOG, is_composite
from services.question_types.shapes import SHAPES
from services.question_types.spec import TypeSpec

#: Where the generated module lives, relative to the repository root.
FRONTEND_MODULE_PATH = PurePosixPath("frontend/lib/question-types.generated.ts")

#: Codes the catalogue renamed, old → new. A bank row holding an old code is
#: moved to the new one by migration 0016, and the old code becomes an alias.
RENAMED_CODES: Dict[str, str] = {
    "STATEMENT_EVAL": "MCQ_STATEMENT_EVAL",
    "ODD_ONE_OUT": "MCQ_ODD_ONE_OUT",
    "SEQUENCING": "MCQ_SEQUENCE",
    "DRAW_COLOUR_TRACE": "DRAW_COLOUR",
    "SPEECH_DEBATE_WRITING": "SPEECH_DEBATE",
}

#: Formats answered by marking the paper itself, which need no ruled lines.
_NO_ANSWER_SPACE = frozenset({"MCQ_4", "MCQ_MULTI", "MARK", "MATCH"})


def _auto_markable(spec: TypeSpec) -> bool:
    if spec.auto_markable is not None:
        return spec.auto_markable
    return next(f.is_auto_markable for f in FAMILIES if f.code == spec.family)


def _axes(spec: TypeSpec) -> Dict[str, Any]:
    return {
        "ref": spec.ref,
        "status": spec.status,
        "shape": spec.shape,
        "format": spec.format,
        "task": spec.task,
        "stimulus": spec.stimulus,
        "container": spec.container,
        "lane": spec.lane,
        "availability": spec.resolved_availability,
        "classes": list(spec.classes),
        "marks": spec.marks,
        "marksRange": list(spec.marks_range),
        "subjects": list(spec.subjects) if spec.subjects else None,
        "options": (
            {
                "min": spec.options.min,
                "max": spec.options.max,
                "multiCorrect": spec.options.multi_correct,
                "fixed": list(spec.options.fixed),
            }
            if spec.options
            else None
        ),
        "route": (
            {"generator": spec.route.generator, "assetType": spec.route.asset_type}
            if spec.route
            else None
        ),
    }


def db_snapshot() -> Dict[str, Any]:
    """Every row migration 0016 seeds, as plain data."""
    types: List[Dict[str, Any]] = []
    for spec in CATALOG.values():
        types.append(
            {
                "code": spec.code,
                "family": spec.family,
                "name": spec.label,
                "description": spec.tests,
                "purpose": spec.brief or None,
                "is_container": spec.is_container,
                "requires_stimulus": spec.requires_stimulus,
                "requires_options": spec.options is not None,
                "requires_figure": spec.requires_figure,
                "produces_figure": spec.produces_figure,
                "is_auto_markable": _auto_markable(spec),
                "is_competency_default": spec.code == "APPLICATION_SCENARIO",
                "needs_answer_space": spec.format not in _NO_ANSWER_SPACE,
                "default_answer_space_lines": spec.answer_lines,
                "is_internal_only": spec.resolved_availability in {"internal", "structural"},
                "content_schema": _axes(spec),
                "answer_schema": {"marking": spec.marking, "example": spec.answer or None},
            }
        )

    # A shape spelled like its own default type ("CASE_STUDY") needs no alias.
    aliases = [
        {"alias": shape.code, "type": shape.default_type, "source": "runtime_shape"}
        for shape in SHAPES
        if shape.code != shape.default_type
    ] + [
        {"alias": old, "type": new, "source": "renamed"}
        for old, new in RENAMED_CODES.items()
    ]

    return {
        "families": [
            {
                "code": family.code,
                "name": family.name,
                "response_mode": family.response_mode,
                "is_auto_markable": family.is_auto_markable,
                "sort_order": family.sort_order,
            }
            for family in FAMILIES
        ],
        "types": types,
        "aliases": aliases,
        "renamed": dict(RENAMED_CODES),
    }


def snapshot_json() -> str:
    return json.dumps(db_snapshot(), indent=1, ensure_ascii=False) + "\n"


def _frontend_entry(spec: TypeSpec) -> Dict[str, Any]:
    return {
        "code": spec.code,
        "label": spec.label,
        "family": spec.family,
        "shape": spec.shape,
        "container": spec.container,
        "stimulus": spec.stimulus,
        "availability": spec.resolved_availability,
        "classes": list(spec.classes),
        "marks": spec.marks,
        "marksRange": list(spec.marks_range),
        "composite": is_composite(spec.code),
        "reason": spec.unavailable_reason,
    }


def frontend_module() -> str:
    """The TypeScript source of `frontend/lib/question-types.generated.ts`."""
    dump = lambda value: json.dumps(value, ensure_ascii=False)  # noqa: E731
    lines = [
        "// Generated by `python manage.py export_question_types` from",
        "// backend/services/question_types. Do not edit by hand.",
        "",
        'export type QuestionTypeAvailability = "available" | "needs_picture" | "internal" | "structural";',
        "",
        "export interface QuestionTypeInfo {",
        "  code: string;",
        "  label: string;",
        "  family: string;",
        "  /** The runtime shape the editor lays the question out as. */",
        "  shape: string;",
        "  container: string;",
        "  stimulus: string;",
        "  availability: QuestionTypeAvailability;",
        "  classes: [number, number];",
        "  marks: number;",
        "  marksRange: [number, number];",
        "  /** Laid out as a head block plus a run of body paragraphs. */",
        "  composite: boolean;",
        "  /** Why an unavailable type cannot be used; empty when it can. */",
        "  reason: string;",
        "}",
        "",
        "export interface QuestionFamilyInfo {",
        "  code: string;",
        "  letter: string;",
        "  name: string;",
        "}",
        "",
        "export const QUESTION_FAMILIES: readonly QuestionFamilyInfo[] = [",
        *[
            f"  {dump({'code': f.code, 'letter': f.letter, 'name': f.name})},"
            for f in FAMILIES
        ],
        "];",
        "",
        "export const QUESTION_TYPES: Readonly<Record<string, QuestionTypeInfo>> = {",
        *[
            f"  {dump(spec.code)}: {dump(_frontend_entry(spec))},"
            for spec in CATALOG.values()
        ],
        "} as Readonly<Record<string, QuestionTypeInfo>>;",
        "",
        "/** Runtime shape → the catalogue type a bare shape name means. */",
        "export const SHAPE_DEFAULT_TYPE: Readonly<Record<string, string>> = {",
        *[f"  {dump(shape.code)}: {dump(shape.default_type)}," for shape in SHAPES],
        "};",
        "",
    ]
    return "\n".join(lines)
