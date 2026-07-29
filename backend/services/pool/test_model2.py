"""Model 2 tests — hybrid paper assembly.

The load-bearing property is stage 5: whatever the review model returns, the
paper that ships is structurally valid. These tests attack that from every
angle an LLM can get it wrong — unknown ids, duplicate ids, missing slots,
wrong marks — and assert the deterministic selection survives each time.
"""

import json
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from django.test import TestCase

from services.pool.model2 import (
    AssembledPaper,
    PaperAssemblyError,
    assemble_paper,
    build_candidates,
    filter_pool,
)
from services.pool.schema import PoolQuestion


@dataclass
class FakeSlot:
    """Stands in for QuestionGenerationSlot — only the fields Model 2 reads."""

    index: int
    marks: int
    question_type: str
    legacy_type: str
    section_title: str = "Section A"


def _question(qid, qtype="MCQ", marks=1, topic="t", blooms="UNDERSTAND",
              difficulty="medium", chapter="Electricity", subject="Science",
              explanation="because"):
    return PoolQuestion(
        id=qid, subject=subject, chapter=chapter, topic=topic, type=qtype,
        blooms=blooms, difficulty=difficulty, marks=marks,
        question=f"Question {qid}?", options=["a", "b", "c", "d"] if qtype == "MCQ" else [],
        answer="a", explanation=explanation,
    )


def _mcq_slots(count, start=1):
    return [
        FakeSlot(index=i, marks=1, question_type="MCQ", legacy_type="MCQ")
        for i in range(start, start + count)
    ]


class FilterPoolTests(TestCase):
    def test_filters_by_subject(self):
        pool = [
            _question("a", subject="Science"),
            _question("b", subject="Mathematics"),
        ]
        self.assertEqual(
            [q.id for q in filter_pool(pool, subject="Science")], ["a"]
        )

    def test_subject_match_is_case_insensitive(self):
        pool = [_question("a", subject="science")]
        self.assertEqual(len(filter_pool(pool, subject="Science")), 1)

    def test_filters_by_chapter(self):
        pool = [
            _question("a", chapter="Electricity"),
            _question("b", chapter="Magnetism"),
        ]
        self.assertEqual(
            [q.id for q in filter_pool(pool, chapters=["Electricity"])], ["a"]
        )

    def test_excludes_ids(self):
        pool = [_question("a"), _question("b")]
        self.assertEqual(
            [q.id for q in filter_pool(pool, exclude_ids=["a"])], ["b"]
        )

    def test_drops_questions_with_empty_text(self):
        blank = _question("a")
        blank.question = "   "
        self.assertEqual(filter_pool([blank]), [])


class BuildCandidatesTests(TestCase):
    def test_fills_every_slot_with_a_distinct_question(self):
        pool = [_question(f"q{i}", topic=f"topic{i}") for i in range(10)]
        assignments, unfilled = build_candidates(pool, _mcq_slots(5))

        self.assertEqual(len(assignments), 5)
        self.assertEqual(unfilled, [])
        ids = [a.question.id for a in assignments]
        self.assertEqual(len(set(ids)), 5, "No question may fill two slots.")

    def test_marks_must_match_exactly(self):
        pool = [_question("a", marks=3)]
        slots = [FakeSlot(index=1, marks=5, question_type="MCQ", legacy_type="MCQ")]
        assignments, unfilled = build_candidates(pool, slots)

        self.assertEqual(assignments, [])
        self.assertEqual(len(unfilled), 1)
        self.assertIn("type and mark value", unfilled[0].reason)

    def test_reports_starvation_separately_from_absence(self):
        # One eligible question, two slots that both want it.
        pool = [_question("only")]
        assignments, unfilled = build_candidates(pool, _mcq_slots(2))

        self.assertEqual(len(assignments), 1)
        self.assertEqual(len(unfilled), 1)
        self.assertIn("already used by another slot", unfilled[0].reason)

    def test_alternates_are_offered_and_never_shared(self):
        pool = [_question(f"q{i}", topic=f"topic{i}") for i in range(12)]
        assignments, _ = build_candidates(pool, _mcq_slots(3), alternates=2)

        for assignment in assignments:
            self.assertEqual(len(assignment.alternates), 2)

        # The offered sets must be pairwise disjoint: an id offered anywhere
        # appears exactly once across all chosen questions and all alternates.
        # That is what lets stage 5 accept any per-slot pick without a
        # duplicate check ever failing on a legitimate swap.
        every_offered = []
        for assignment in assignments:
            every_offered.append(assignment.question.id)
            every_offered.extend(alt.id for alt in assignment.alternates)

        self.assertEqual(
            len(every_offered), len(set(every_offered)),
            f"An id was offered to more than one slot: {every_offered}",
        )

    def test_thin_pool_yields_fewer_alternates_rather_than_starving_slots(self):
        # 4 questions, 3 slots: every slot must still be FILLED, even though
        # there is only one leftover to hand out as an alternate.
        pool = [_question(f"q{i}", topic=f"topic{i}") for i in range(4)]
        assignments, unfilled = build_candidates(pool, _mcq_slots(3), alternates=2)

        self.assertEqual(len(assignments), 3)
        self.assertEqual(unfilled, [])
        self.assertEqual(sum(len(a.alternates) for a in assignments), 1)

    def test_prefers_topic_diversity(self):
        # Five questions on one topic, five spread across others.
        pool = [_question(f"same{i}", topic="repeated") for i in range(5)]
        pool += [_question(f"diff{i}", topic=f"unique{i}") for i in range(5)]

        assignments, _ = build_candidates(pool, _mcq_slots(5), alternates=0)
        topics = [a.question.topic for a in assignments]

        self.assertGreaterEqual(
            len(set(topics)), 4,
            f"Expected a spread of topics, got {topics}",
        )

    def test_spreads_across_chapters(self):
        pool = [_question(f"e{i}", chapter="Electricity", topic=f"e{i}") for i in range(6)]
        pool += [_question(f"m{i}", chapter="Magnetism", topic=f"m{i}") for i in range(6)]

        assignments, _ = build_candidates(pool, _mcq_slots(6), alternates=0)
        chapters = {a.question.chapter for a in assignments}

        self.assertEqual(chapters, {"Electricity", "Magnetism"})

    def test_most_constrained_slot_is_filled_first(self):
        # Two 1-mark MCQs available; one 5-mark long answer available.
        # Filling in blueprint order would be fine here, but if the scarce
        # 5-mark question were consumed by a permissive slot the long-answer
        # slot would starve.
        pool = [
            _question("mcq1", topic="a"),
            _question("mcq2", topic="b"),
            _question("long1", qtype="LONG_ANSWER", marks=5, topic="c"),
        ]
        slots = [
            FakeSlot(index=1, marks=1, question_type="MCQ", legacy_type="MCQ"),
            FakeSlot(index=2, marks=5, question_type="LONG_ANSWER", legacy_type="LONG"),
        ]
        assignments, unfilled = build_candidates(pool, slots)

        self.assertEqual(unfilled, [])
        by_index = {a.slot.index: a.question.id for a in assignments}
        self.assertEqual(by_index[2], "long1")

    def test_assignments_come_back_in_slot_order(self):
        pool = [_question(f"q{i}", topic=f"t{i}") for i in range(6)]
        assignments, _ = build_candidates(pool, _mcq_slots(4))
        indices = [a.slot.index for a in assignments]
        self.assertEqual(indices, sorted(indices))

    def test_is_deterministic_for_a_given_seed(self):
        pool = [_question(f"q{i}", topic=f"t{i}") for i in range(20)]
        first, _ = build_candidates(pool, _mcq_slots(6), seed=99)
        second, _ = build_candidates(pool, _mcq_slots(6), seed=99)

        self.assertEqual(
            [a.question.id for a in first], [a.question.id for a in second]
        )


class _FakeProvider:
    def __init__(self, content):
        self.content = content
        self.requests = []

    def chat(self, request):
        self.requests.append(request)
        if isinstance(self.content, Exception):
            raise self.content
        response = MagicMock()
        response.content = self.content
        return response


class AssemblePaperTests(TestCase):
    def setUp(self):
        self.pool = [_question(f"q{i}", topic=f"topic{i}") for i in range(12)]
        self.slots = _mcq_slots(4)

    def _assemble(self, content, **kwargs):
        provider = _FakeProvider(content)
        with patch("services.pool.model2.OpenAIProvider", return_value=provider):
            paper = assemble_paper(
                self.pool, self.slots, subject="Science", class_num=10, **kwargs
            )
        return paper, provider

    def test_review_disabled_skips_the_model_entirely(self):
        paper, provider = self._assemble("unused", use_review=False)

        self.assertEqual(provider.requests, [])
        self.assertFalse(paper.review_applied)
        self.assertEqual(paper.total_questions, 4)

    def test_valid_review_is_applied_and_swaps_are_counted(self):
        provider = _FakeProvider("")
        with patch("services.pool.model2.OpenAIProvider", return_value=provider):
            baseline = assemble_paper(
                self.pool, self.slots, subject="Science", use_review=False
            )

        # Swap slot 1 to its first alternate; keep the rest.
        selections = []
        for assignment in baseline.assignments:
            index = assignment.slot.index
            if index == 1 and assignment.alternates:
                selections.append({"slot": index, "id": assignment.alternates[0].id})
            else:
                selections.append({"slot": index, "id": assignment.question.id})

        paper, _ = self._assemble(json.dumps({"selections": selections}))

        self.assertTrue(paper.review_applied)
        self.assertEqual(paper.review_swaps, 1)
        self.assertEqual(paper.total_questions, 4)

    def test_review_naming_an_unoffered_id_is_rejected_wholesale(self):
        selections = [
            {"slot": slot.index, "id": "totally-made-up"} for slot in self.slots
        ]
        paper, _ = self._assemble(json.dumps({"selections": selections}))

        self.assertFalse(paper.review_applied)
        self.assertIn("not offered for that slot", paper.review_rejected_reason)
        self.assertEqual(paper.total_questions, 4, "The paper still ships.")

    def test_review_reusing_one_id_across_slots_is_rejected(self):
        provider = _FakeProvider("")
        with patch("services.pool.model2.OpenAIProvider", return_value=provider):
            baseline = assemble_paper(
                self.pool, self.slots, subject="Science", use_review=False
            )
        duplicated = baseline.assignments[0].question.id
        selections = [{"slot": s.index, "id": duplicated} for s in self.slots]

        paper, _ = self._assemble(json.dumps({"selections": selections}))

        self.assertFalse(paper.review_applied)
        self.assertEqual(paper.total_questions, 4)

    def test_review_with_missing_slots_is_rejected(self):
        paper, _ = self._assemble(
            json.dumps({"selections": [{"slot": 1, "id": "whatever"}]})
        )
        self.assertFalse(paper.review_applied)
        self.assertIn("expected 4 selections", paper.review_rejected_reason)

    def test_unparseable_review_is_rejected(self):
        paper, _ = self._assemble("I'm afraid I can't do that.")
        self.assertFalse(paper.review_applied)
        self.assertEqual(paper.total_questions, 4)

    def test_review_call_failure_is_contained(self):
        paper, _ = self._assemble(RuntimeError("model down"))
        self.assertFalse(paper.review_applied)
        self.assertIn("review call failed", paper.review_rejected_reason)
        self.assertEqual(paper.total_questions, 4)

    def test_marks_survive_every_rejection_path(self):
        for content in [
            "garbage",
            json.dumps({"selections": []}),
            json.dumps({"selections": [{"slot": 1, "id": "nope"}]}),
        ]:
            with self.subTest(content=content[:24]):
                paper, _ = self._assemble(content)
                self.assertEqual(paper.total_marks, 4)
                self.assertEqual(paper.total_questions, 4)

    def test_empty_plan_raises(self):
        with self.assertRaises(PaperAssemblyError):
            assemble_paper(self.pool, [], subject="Science")

    def test_pool_with_no_matching_subject_raises(self):
        with self.assertRaises(PaperAssemblyError) as ctx:
            assemble_paper(self.pool, self.slots, subject="Mathematics")
        self.assertIn("subject and chapters", str(ctx.exception))

    def test_pool_that_cannot_fill_any_slot_raises(self):
        pool = [_question("only", qtype="LONG_ANSWER", marks=5)]
        with self.assertRaises(PaperAssemblyError) as ctx:
            assemble_paper(pool, self.slots, subject="Science", use_review=False)
        self.assertIn("could not fill a single slot", str(ctx.exception))

    def test_partial_fill_reports_unfilled_but_still_produces_a_paper(self):
        pool = [_question(f"q{i}", topic=f"t{i}") for i in range(2)]
        provider = _FakeProvider("")
        with patch("services.pool.model2.OpenAIProvider", return_value=provider):
            paper = assemble_paper(
                pool, self.slots, subject="Science", use_review=False
            )
        self.assertEqual(paper.total_questions, 2)
        self.assertEqual(len(paper.unfilled), 2)

    def test_questions_in_slot_order(self):
        paper, _ = self._assemble("garbage")
        ordered = paper.questions_in_slot_order()
        self.assertEqual(len(ordered), 4)

    def test_review_prompt_carries_only_metadata_not_full_questions(self):
        _, provider = self._assemble("garbage")
        prompt = str(provider.requests[0].messages[-1].content)

        # The wire format truncates stems and omits answers/explanations —
        # this is what keeps the review call cheap.
        self.assertIn('"stem"', prompt)
        self.assertNotIn('"explanation"', prompt)
        self.assertNotIn('"answer"', prompt)


def _figure_question(qid, *, image=None, topic=None):
    q = _question(qid, qtype="DIAGRAM", marks=1, topic=topic or f"topic-{qid}")
    q.image = image
    return q


def _figure_slot(index=1):
    return FakeSlot(index=index, marks=1, question_type="DIAGRAM", legacy_type="DIAGRAM")


class FigureSlotTests(TestCase):
    """A figure slot must be filled by a question that has a figure.

    The reported failure: "10 image based questions" produced ten questions
    with no images, even though ten images had been drawn and paid for.

    The pool is the reason. Model 1 writes text from chapter markdown and
    cannot draw, so a DIAGRAM batch yields questions that REFER to a figure
    they do not carry; the image stage produces the few that really have one.
    Both land in the same pool typed DIAGRAM, and the text-only ones outnumber
    the real ones several times over — 60 against 10 in the reported run. With
    no preference in the scorer, Model 2 picked from the majority.
    """

    def test_a_figure_slot_takes_the_question_that_has_a_figure(self):
        pool = [
            _figure_question("text-1"),
            _figure_question("text-2"),
            _figure_question("with-image", image="/media/generated_diagrams/a.png"),
            _figure_question("text-3"),
        ]
        assignments, unfilled = build_candidates(pool, [_figure_slot()], seed=1)
        self.assertEqual(unfilled, [])
        self.assertEqual(assignments[0].question.id, "with-image")

    def test_it_holds_when_text_questions_swamp_the_pool(self):
        # The real ratio from the reported run: 60 text, 10 with images.
        pool = [_figure_question(f"text-{i}") for i in range(60)]
        pool += [
            _figure_question(f"img-{i}", image=f"/media/generated_diagrams/{i}.png")
            for i in range(10)
        ]
        slots = [_figure_slot(i) for i in range(1, 11)]

        assignments, unfilled = build_candidates(pool, slots, seed=7)

        self.assertEqual(unfilled, [])
        chosen = [a.question for a in assignments]
        self.assertEqual(len(chosen), 10)
        without = [q.id for q in chosen if not (q.image or "").strip()]
        self.assertEqual(
            without, [], f"figure slots filled with text questions: {without}"
        )

    def test_a_figure_slot_is_still_filled_when_no_image_exists(self):
        # Preference, not eligibility. A blank slot is worse than one of the
        # wrong shape — a teacher can replace a question, not a hole.
        pool = [_figure_question("text-1"), _figure_question("text-2")]
        assignments, unfilled = build_candidates(pool, [_figure_slot()], seed=1)
        self.assertEqual(unfilled, [])
        self.assertIsNotNone(assignments[0].question)

    def test_the_preference_does_not_leak_to_other_slot_types(self):
        from services.pool.model2 import _slot_wants_image

        self.assertFalse(
            _slot_wants_image(FakeSlot(1, 2, "SHORT_ANSWER", "SHORT"))
        )
        self.assertFalse(_slot_wants_image(FakeSlot(1, 1, "MCQ", "MCQ")))
        self.assertTrue(_slot_wants_image(_figure_slot()))

    def test_an_explicit_requires_image_flag_also_counts(self):
        # The CBSE blueprint path marks picture/map slots this way rather than
        # by question type.
        from services.pool.model2 import _slot_wants_image

        slot = FakeSlot(1, 3, "SHORT_ANSWER", "SHORT")
        slot.requires_image = True
        self.assertTrue(_slot_wants_image(slot))

    def test_alternates_for_a_figure_slot_also_carry_figures(self):
        # An alternate is offered as a swap for the chosen question, so one
        # without a figure silently breaks the paper when taken.
        pool = [
            _figure_question(f"img-{i}", image=f"/media/generated_diagrams/{i}.png")
            for i in range(4)
        ]
        pool += [_figure_question(f"text-{i}") for i in range(6)]

        assignments, _ = build_candidates(pool, [_figure_slot()], alternates=2, seed=3)
        alternates = assignments[0].alternates
        self.assertTrue(alternates, "expected alternates to be offered")
        for alternate in alternates:
            self.assertTrue(
                (alternate.image or "").strip(), f"alternate {alternate.id} has no figure"
            )
