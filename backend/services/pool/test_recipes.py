"""Recipe tests — the pool must be able to fill the blueprint it is built for.

The regression these guard is subtle and was live in production: the fixed
per-subject recipes only produce atomic 1–5 mark questions, but the CBSE
language blueprints ask for composite 6/10/12-mark slots. Because `slot_accepts`
matches on exact marks, a pool without those mark values leaves most of a
language paper empty (the real symptom: an English paper that came out with 4
questions instead of 11). `batches_from_plan` fixes that by deriving the recipe
from the plan itself, so every shape the blueprint needs exists in the pool.
"""

from dataclasses import dataclass

from django.test import TestCase

from services.assets import DEFAULT_GENERATOR, partition_plan
from services.generation_router import build_question_plan
from services.pool.model2 import assemble_paper
from services.pool.recipes import batches_for_subject, batches_from_plan
from services.pool.schema import PoolQuestion, compute_content_hash
from utils.ids import generate_id


@dataclass
class FakeSlot:
    index: int
    marks: int
    question_type: str
    legacy_type: str = "SHORT"
    section_title: str = "Section A"
    instruction_hint: str = ""


def _pool_from_batches(
    batches,
    *,
    chapters=("ChA", "ChB", "ChC"),
    generator=DEFAULT_GENERATOR,
):
    """Build a synthetic pool as if each chapter produced the derived recipe."""
    pool = []
    for chapter in chapters:
        for batch in batches:
            for quota in batch.quotas:
                for i in range(quota.count):
                    text = f"{quota.type} {quota.marks}m {chapter} #{i}"
                    pool.append(PoolQuestion(
                        id=generate_id(), subject="English", chapter=chapter,
                        topic=f"{chapter}-{quota.type}", type=quota.type,
                        blooms="UNDERSTAND", difficulty="medium",
                        marks=quota.marks, question=text,
                        generator=generator,
                        content_hash=compute_content_hash("English", chapter, text),
                    ))
    return pool


def _asset_pool_for(slots, *, per_slot=2):
    """Stand-in for what the asset generators return for their slots."""
    pool = []
    for slot in slots:
        for i in range(per_slot):
            text = f"{slot.asset_type} candidate {i} for Q{slot.index}"
            pool.append(PoolQuestion(
                id=generate_id(), subject="English",
                chapter=f"{slot.generator} bank",
                topic=f"{slot.asset_type}-{i}", type=slot.question_type,
                blooms="ANALYZE", difficulty="medium", marks=slot.marks,
                question=text, generator=slot.generator,
                asset_type=slot.asset_type,
                content_hash=compute_content_hash("English", slot.generator, text),
            ))
    return pool


class BatchesFromPlanTests(TestCase):
    def test_covers_every_plan_shape(self):
        plan = [
            FakeSlot(index=1, marks=10, question_type="READING_COMP"),
            FakeSlot(index=2, marks=10, question_type="READING_COMP"),
            FakeSlot(index=3, marks=6, question_type="LONG_ANSWER"),
            FakeSlot(index=4, marks=5, question_type="LETTER"),
        ]
        batches = batches_from_plan(plan, target_total=0)
        shapes = {(q.type, q.marks) for b in batches for q in b.quotas}
        self.assertEqual(
            shapes,
            {("READING_COMP", 10), ("LONG_ANSWER", 6), ("LETTER", 5)},
        )
        # The two-slot shape is counted twice.
        rc = next(q for b in batches for q in b.quotas if q.type == "READING_COMP")
        self.assertEqual(rc.count, 2)

    def test_empty_plan_yields_no_batches(self):
        self.assertEqual(batches_from_plan([], target_total=13), [])
        self.assertEqual(
            batches_from_plan([FakeSlot(index=1, marks=0, question_type="")]), []
        )

    def test_scaling_preserves_every_shape(self):
        plan = [FakeSlot(index=i, marks=10, question_type="READING_COMP") for i in range(2)]
        plan.append(FakeSlot(index=3, marks=12, question_type="SHORT_ANSWER"))
        batches = batches_from_plan(plan, target_total=20)
        shapes = {(q.type, q.marks) for b in batches for q in b.quotas}
        self.assertIn(("SHORT_ANSWER", 12), shapes)
        self.assertIn(("READING_COMP", 10), shapes)


class EnglishBlueprintCoverageTests(TestCase):
    """The end-to-end property: the derived pool fills the real English paper."""

    def test_fixed_language_recipe_lacks_the_needed_marks(self):
        # Documents WHY the derived recipe is needed: the fixed recipe only has
        # {1,2,3,5}-mark questions, so 6/10/12-mark slots can never be filled.
        fixed = batches_for_subject("english", target_total=0)
        marks = {q.marks for b in fixed for q in b.quotas}
        self.assertFalse({6, 10, 12} & marks)

    def test_derived_pool_fills_all_eleven_slots(self):
        """Both pools together fill the paper; neither can do it alone.

        Model 1's recipe is now derived from the LITERATURE slots only — the
        other five are owned by asset generators — so this checks the two
        halves compose back into a complete 80-mark paper.
        """
        plan = list(build_question_plan(
            topic="English", difficulty="medium", count=-1,
            class_num=10, subject="English", count_variation="cbse",
        ))
        self.assertEqual(len(plan), 11)

        routed = partition_plan(plan)
        literature = routed[DEFAULT_GENERATOR]
        assets = [s for n, slots in routed.items() if n != DEFAULT_GENERATOR for s in slots]
        self.assertEqual(len(literature), 6)
        self.assertEqual(len(assets), 5)

        batches = batches_from_plan(literature, target_total=13)
        pool = _pool_from_batches(batches) + _asset_pool_for(assets)

        paper = assemble_paper(
            pool, plan, subject="English", class_num=10,
            difficulty="medium", use_review=False,
        )
        self.assertEqual(paper.total_questions, 11)
        self.assertEqual(paper.total_marks, 80)
        self.assertEqual(paper.unfilled, [])

    def test_textbook_pool_alone_cannot_fill_the_asset_sections(self):
        """The regression this whole refactor exists to prevent.

        A pool built entirely from uploaded chapters used to be a legal fill
        for every slot, which is how Reading and Writing ended up full of
        Literature questions. Provenance now makes those five slots unfillable
        from the textbook — they are reported unfilled rather than filled wrong.
        """
        plan = list(build_question_plan(
            topic="English", difficulty="medium", count=-1,
            class_num=10, subject="English", count_variation="cbse",
        ))
        # A generous textbook pool covering every shape the paper asks for.
        pool = _pool_from_batches(batches_from_plan(plan, target_total=40))

        paper = assemble_paper(
            pool, plan, subject="English", class_num=10,
            difficulty="medium", use_review=False,
        )
        self.assertEqual(paper.total_questions, 6)
        self.assertEqual(len(paper.unfilled), 5)
        self.assertEqual(
            {s.slot.generator for s in paper.unfilled},
            {"reading_asset_pool", "grammar_asset_pool", "writing_asset_pool"},
        )
        for assignment in paper.assignments:
            self.assertTrue(assignment.question.uses_uploaded_content)

    def test_blueprint_hints_reach_model_1(self):
        """Composite literature slots carry their structure into the recipe."""
        plan = list(build_question_plan(
            topic="English", difficulty="medium", count=-1,
            class_num=10, subject="English", count_variation="cbse",
        ))
        literature = partition_plan(plan)[DEFAULT_GENERATOR]
        batches = batches_from_plan(literature, target_total=0)

        hints = {
            (q.type, q.marks): q.hints
            for b in batches
            for q in b.quotas
        }
        self.assertIn("any four of the following five", hints[("SHORT_ANSWER", 12)][0])
        self.assertIn("any two of the following three", hints[("SHORT_ANSWER", 6)][0])
