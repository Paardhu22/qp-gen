"""Re-bless the prompt snapshot after an intentional prompt change.

Run from backend/: .venv/bin/python scratch/regen_prompt_snapshot.py
Mirrors the exact assembly in
apps/question_generation/tests/test_prompt_snapshots.py.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from apps.question_generation.domain.context import (
    GenerationConstraints,
    GenerationContext,
)
from apps.question_generation.domain.enums import AcademicClass, EducationBoard
from apps.question_generation.services.prompting.assembler import (
    PromptAssembler,
    default_system_rules,
)

context = GenerationContext(
    subject="Science",
    board=EducationBoard.CBSE,
    academic_class=AcademicClass.CLASS_10,
    difficulty="medium",
    retrieved_chunks=[
        "# Chapter 11 Electricity\n## Concept: Ohm's Law\n\n"
        "Ohm's law states that the current through a conductor between two points is directly proportional "
        "to the voltage across the two points."
    ],
    generation_constraints=GenerationConstraints(count=10, difficulty="medium"),
    prompt_version="v1",
)

blueprint_instructions = (
    "ACADEMIC BLUEPRINT INSTRUCTIONS (MANDATORY):\n"
    "- Board: CBSE | Class: CLASS_10 | Exam: FINAL\n"
    "- Overall Difficulty Target: MEDIUM\n"
    "- You MUST generate exactly 10 questions in total.\n"
    "- Your questions MUST strictly use the provided PDF context.\n"
    "- Distribute questions across MCQ, ASSERTION_REASON, SHORT, LONG, and CASE_STUDY types logically."
)

assembler = PromptAssembler(version_id="v1")
document = assembler.assemble(
    context=context,
    system_rules=default_system_rules(context.generation_constraints),
    output_schema='{"sections": [{"title": "Section A", "questions": []}]}',
    blueprint_instructions=blueprint_instructions,
)

path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "apps/question_generation/tests/snapshots/science_cbse_class10_final.txt",
)
with open(path, "w", encoding="utf-8") as fh:
    fh.write(document.render().strip() + "\n")
print("snapshot regenerated:", path)
