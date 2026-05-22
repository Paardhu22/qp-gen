import os
import unittest

from apps.question_generation.domain.context import GenerationConstraints, GenerationContext
from apps.question_generation.domain.enums import AcademicClass, EducationBoard
from apps.question_generation.services.prompting.assembler import PromptAssembler, default_system_rules


class PromptSnapshotTests(unittest.TestCase):
    def test_science_cbse_class10_prompt_snapshot(self) -> None:
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

        snapshot_path = os.path.join(
            os.path.dirname(__file__), "snapshots", "science_cbse_class10_final.txt"
        )
        with open(snapshot_path, "r", encoding="utf-8") as handle:
            expected = handle.read().strip()

        self.assertEqual(document.render().strip(), expected)


if __name__ == "__main__":
    unittest.main()
