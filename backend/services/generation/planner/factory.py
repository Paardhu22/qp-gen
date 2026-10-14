"""Builds one fully-specified question slot: its instruction text and retrieval query included."""

import dataclasses
from typing import Dict, Any, Optional, Sequence

from services.generation.pool.schema import DEFAULT_GENERATOR as POOL_GENERATOR
from services.generation.planner.slot_prompts import _slot_instruction, build_retrieval_query
from services.generation.planner.slots import QuestionGenerationSlot, _legacy_question_type


def _make_slot(
    *,
    index: int,
    section_title: str,
    subject: str,
    stream: str,
    qtype_name: str,
    marks: int,
    difficulty: str,
    class_num: int,
    topic: str,
    instructions: str,
    choice_required: bool = False,
    requires_figure: bool = False,
    instruction_hint: str = "",
    mode: str = "CONTENT",
    generator: str = POOL_GENERATOR,
    asset_type: str = "",
    constraints: Optional[Dict[str, Any]] = None,
    validation: Sequence[str] = (),
) -> QuestionGenerationSlot:
    legacy_type = _legacy_question_type(qtype_name)
    retrieval_query = build_retrieval_query(
        mode=mode,
        topic=topic,
        subject=subject,
        stream=stream,
        qtype_name=qtype_name,
        marks=marks,
        difficulty=difficulty,
        class_num=class_num,
        choice_required=choice_required,
        instruction_hint=instruction_hint,
        instructions=instructions,
    )
    draft = QuestionGenerationSlot(
        index=index,
        section_title=section_title,
        subject=subject,
        stream=stream,
        question_type=qtype_name,
        legacy_type=legacy_type,
        marks=marks,
        difficulty=difficulty,
        class_num=class_num,
        exact_instruction="",
        retrieval_query=retrieval_query,
        choice_required=choice_required,
        requires_figure=requires_figure,
        instruction_hint=instruction_hint,
        generation_mode=str(mode).upper(),
        generator=str(generator or POOL_GENERATOR),
        asset_type=str(asset_type or ""),
        constraints=dict(constraints or {}),
        validation=tuple(validation or ()),
    )
    return dataclasses.replace(draft, exact_instruction=_slot_instruction(draft))
