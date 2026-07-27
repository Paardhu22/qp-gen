"""The three asset generators, driven against a stubbed model.

The assertions that matter are structural rather than literary: that the asset
dataclasses coerce a model's JSON into something printable, that the
blueprint's constraints actually drive validation, and — the architectural
one — that everything a generator emits is stamped with its provenance so the
assembler can tell it apart from a textbook question.
"""

import json
from typing import Any, Dict, List

from django.test import TestCase

from services.assets.base import AssetRequest
from services.assets.grammar import GrammarAssetGenerator
from services.assets.reading import ReadingAssetGenerator
from services.assets.registry import DEFAULT_GENERATOR
from services.assets.runner import generate_assets_for_plan
from services.assets.schema import (
    GrammarAsset,
    GrammarTaskSet,
    ReadingAsset,
    WritingAsset,
)
from services.assets.validation import validate_asset
from services.assets.writing import WritingAssetGenerator
from services.generation_router import build_question_plan
from services.pool.schema import PoolValidationError


def _english_plan():
    return list(
        build_question_plan(
            topic="English", difficulty="medium", count=-1,
            class_num=10, subject="English", count_variation="cbse",
        )
    )


def _slot(asset_type):
    return next(s for s in _english_plan() if s.asset_type == asset_type)


# ── Fixtures shaped like what the models actually return ────────────────


def _reading_payload(marks_pattern=(1, 1, 1, 1, 1, 2, 1, 2), paragraphs=6):
    return {
        "topic": "Indigenous crafts",
        "passage_style": "discursive",
        "difficulty": "medium",
        "reading_level": "class_10",
        "passage": "\n\n".join(
            f"Paragraph {i} " + "word " * 60 for i in range(1, paragraphs + 1)
        ),
        "paragraph_map": [f"gist {i}" for i in range(1, paragraphs + 1)],
        "questions": [
            {
                "question": f"Sub-question {i}",
                "marks": m,
                "paragraph": (i % paragraphs) + 1,
                "skill": "inference",
                "options": ["A", "B", "C", "D"] if m == 1 else [],
                "answer": f"answer {i}",
            }
            for i, m in enumerate(marks_pattern)
        ],
    }


def _grammar_payload(topics):
    return [
        {
            "grammar_topic": topic,
            "context": "a market-research report",
            "question": f"Task on {topic}: fill the blank ______.",
            "options": ["A", "B", "C", "D"],
            "answer": f"answer for {topic}",
            "difficulty": "medium",
            "explanation": f"the {topic} rule",
        }
        for topic in topics
    ]


def _writing_payload(formats):
    return [
        {
            "task_type": fmt,
            "role": "Club in-charge",
            "audience": "Education Secretary",
            "scenario": (
                f"As Vaibhav, write a {fmt.replace('_', ' ')} in about 120 words "
                "about starting eco-clubs in nearby schools."
            ),
            "word_limit": 120,
            "stimulus": (
                [
                    {"title": "Excerpt 1", "body": "First speaker's letter."},
                    {"title": "Excerpt 2", "body": "Second speaker's letter."},
                ]
                if fmt == "analytical_paragraph"
                else []
            ),
            "rubric": ["Format 1", "Content 2", "Expression 2"],
            "model_answer": "A full sample response.",
            "difficulty": "medium",
        }
        for fmt in formats
    ]


class _StubProvider:
    """Returns a canned JSON body, recording every prompt it was given."""

    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.requests: List[Any] = []

    def chat(self, request):
        self.requests.append(request)
        body = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]

        class _Response:
            content = json.dumps(body)

        return _Response()

    def prompt_text(self) -> str:
        return "\n".join(
            str(m.content) for r in self.requests for m in r.messages
        )


# ── Asset dataclasses ───────────────────────────────────────────────────


class ReadingAssetTests(TestCase):
    def test_coerces_a_model_payload(self):
        asset = ReadingAsset.from_raw(_reading_payload())
        self.assertEqual(len(asset.questions), 8)
        self.assertEqual(asset.total_marks, 10)
        self.assertEqual(len(asset.paragraphs), 6)

    def test_rejects_a_passage_with_no_questions(self):
        with self.assertRaises(PoolValidationError):
            ReadingAsset.from_raw({"passage": "text", "questions": []})

    def test_rejects_an_empty_passage(self):
        with self.assertRaises(PoolValidationError):
            ReadingAsset.from_raw({"passage": "", "questions": [{"question": "q"}]})

    def test_renders_a_numbered_passage_and_marked_sub_questions(self):
        rendered = ReadingAsset.from_raw(_reading_payload()).render_question()
        self.assertIn("Read the following passage.", rendered)
        self.assertIn("Answer the following questions, based on the passage above.", rendered)
        self.assertIn("I. Sub-question 0", rendered)
        self.assertIn("[2]", rendered)  # the 2-mark parts print their marks
        self.assertIn("(Paragraph ", rendered)

    def test_answer_key_covers_every_sub_question(self):
        key = ReadingAsset.from_raw(_reading_payload()).render_answer()
        self.assertEqual(len(key.strip().splitlines()), 8)

    def test_composite_parts_rejoin_into_the_rendered_question(self):
        # The editor lays the parts out as separate blocks so a long passage
        # can break across pages. They must still be the SAME text the paper
        # has always carried, or the two renderings drift.
        asset = ReadingAsset.from_raw(_reading_payload())
        parts = asset.composite_parts()
        rejoined = "\n\n".join(
            [parts["preamble"], *parts["body"], *parts["subQuestions"]]
        )
        self.assertEqual(rejoined, asset.render_question())

    def test_composite_parts_are_split_on_real_newlines(self):
        # A literal "\\n" here reaches the editor as two characters, collapses
        # the passage into one unsplittable block and prints the escape.
        parts = ReadingAsset.from_raw(_reading_payload(paragraphs=6)).composite_parts()
        self.assertEqual(len(parts["subQuestions"]), 8)
        # 6 numbered paragraphs + the word-count line + the lead-in.
        self.assertEqual(len(parts["body"]), 8)
        for chunk in [parts["preamble"], *parts["body"], *parts["subQuestions"]]:
            self.assertNotIn("\\n", chunk)


class GrammarAssetTests(TestCase):
    def test_a_task_set_prints_its_attempt_instruction(self):
        tasks = [GrammarAsset.from_raw(t) for t in _grammar_payload(["modal_gap_fill"] * 12)]
        rendered = GrammarTaskSet(tasks=tasks, attempt=10).render_question()
        self.assertIn("Complete any 10 of 12", rendered)
        self.assertIn("XII.", rendered)

    def test_composite_parts_rejoin_into_the_rendered_question(self):
        tasks = [GrammarAsset.from_raw(t) for t in _grammar_payload(["modal_gap_fill"] * 12)]
        task_set = GrammarTaskSet(tasks=tasks, attempt=10)
        parts = task_set.composite_parts()
        self.assertEqual(len(parts["subQuestions"]), 12)
        rejoined = "\n\n".join(
            [parts["preamble"], *parts["body"], *parts["subQuestions"]]
        )
        self.assertEqual(rejoined, task_set.render_question())

    def test_a_task_without_a_grammar_topic_is_rejected(self):
        with self.assertRaises(PoolValidationError):
            GrammarAsset.from_raw({"question": "fill the blank", "answer": "x"})


class WritingAssetTests(TestCase):
    def test_stimulus_blocks_are_printed_inside_the_question(self):
        asset = WritingAsset.from_raw(_writing_payload(["analytical_paragraph"])[0])
        rendered = asset.render_question()
        self.assertIn("Excerpt 1", rendered)
        self.assertIn("Excerpt 2", rendered)

    def test_the_model_answer_stays_in_the_answer_key(self):
        asset = WritingAsset.from_raw(_writing_payload(["formal_letter_to_authority"])[0])
        self.assertNotIn("A full sample response", asset.render_question())
        self.assertIn("A full sample response", asset.render_answer())


# ── Validation is driven by the blueprint ───────────────────────────────


class ValidationTests(TestCase):
    def test_a_correct_reading_asset_passes_its_declared_rules(self):
        slot = _slot("discursive_passage")
        self.assertEqual(validate_asset(ReadingAsset.from_raw(_reading_payload()), slot), [])

    def test_wrong_sub_question_marks_are_caught(self):
        slot = _slot("discursive_passage")
        asset = ReadingAsset.from_raw(_reading_payload(marks_pattern=(1, 1, 1)))
        problems = validate_asset(asset, slot)
        self.assertTrue(any("sub_question_marks_sum" in p for p in problems))
        self.assertTrue(any("sub_question_count" in p for p in problems))

    def test_a_short_passage_is_caught(self):
        slot = _slot("discursive_passage")
        payload = _reading_payload()
        payload["passage"] = "far too short"
        payload["paragraph_map"] = ["gist"]
        problems = validate_asset(ReadingAsset.from_raw(payload), slot)
        self.assertTrue(any("passage_word_count" in p for p in problems))

    def test_a_stray_paragraph_reference_is_caught(self):
        slot = _slot("discursive_passage")
        payload = _reading_payload()
        payload["questions"][0]["paragraph"] = 99
        problems = validate_asset(ReadingAsset.from_raw(payload), slot)
        self.assertTrue(any("paragraph_reference_bounds" in p for p in problems))

    def test_repeated_grammar_topics_are_caught(self):
        slot = _slot("grammar_task_set")
        tasks = [GrammarAsset.from_raw(t) for t in _grammar_payload(["modal_gap_fill"] * 12)]
        problems = validate_asset(GrammarTaskSet(tasks=tasks, attempt=10), slot)
        self.assertTrue(any("distinct_grammar_topics" in p for p in problems))

    def test_a_word_limit_that_contradicts_the_blueprint_is_caught(self):
        slot = _slot("formal_letter_to_authority")  # blueprint asks for ~120
        payload = _writing_payload(["formal_letter_to_authority"])[0]
        payload["scenario"] = "Write a letter to the Education Secretary in about 40 words."
        payload["word_limit"] = 40
        problems = validate_asset(WritingAsset.from_raw(payload), slot)
        self.assertTrue(any("word_limit_declared" in p for p in problems), problems)

    def test_the_blueprint_word_limit_passes(self):
        slot = _slot("formal_letter_to_authority")
        payload = _writing_payload(["formal_letter_to_authority"])[0]
        self.assertEqual(validate_asset(WritingAsset.from_raw(payload), slot), [])

    def test_a_missing_stimulus_is_caught(self):
        slot = _slot("analytical_paragraph")
        payload = _writing_payload(["analytical_paragraph"])[0]
        payload["stimulus"] = []
        problems = validate_asset(WritingAsset.from_raw(payload), slot)
        self.assertTrue(any("stimulus_present" in p for p in problems))

    def test_pretending_to_depend_on_a_textbook_is_caught(self):
        """A generator has no upload, so this can only be the model bluffing —
        and a sub-question that says 'as studied in the chapter' is
        unanswerable however good the passage is."""
        slot = _slot("discursive_passage")
        payload = _reading_payload()
        payload["questions"][0]["question"] = "Explain this, as studied in the chapter."
        problems = validate_asset(ReadingAsset.from_raw(payload), slot)
        self.assertTrue(any("self_contained" in p for p in problems))


# ── Generators ──────────────────────────────────────────────────────────


class ReadingGeneratorTests(TestCase):
    def setUp(self):
        self.slots = [s for s in _english_plan() if s.generator == "reading_asset_pool"]

    def _run(self, provider):
        generator = ReadingAssetGenerator()
        request = AssetRequest(
            slots=tuple(self.slots), subject="English", subject_norm="english",
            class_num=10, difficulty="medium", pool_id="p1", over_provision=2,
        )
        with self.settings(ASSET_MODEL="stub-model"):
            import services.assets.llm as llm

            original = llm.OpenAIProvider
            llm.OpenAIProvider = lambda: provider
            try:
                return generator.generate(request)
            finally:
                llm.OpenAIProvider = original

    def test_produces_provenance_tagged_questions_for_every_slot(self):
        provider = _StubProvider([{"assets": [_reading_payload(), _reading_payload()]}])
        result = self._run(provider)

        self.assertEqual(result.failures, [])
        self.assertEqual(len(result.questions), 4)  # 2 slots × 2 candidates
        for question in result.questions:
            self.assertEqual(question.generator, "reading_asset_pool")
            self.assertEqual(question.source_type, "reading_asset")
            self.assertEqual(question.marks, 10)
            self.assertEqual(question.type, "READING_COMP")
            self.assertFalse(question.uses_uploaded_content)

    def test_the_structured_asset_survives_onto_the_question(self):
        provider = _StubProvider([{"assets": [_reading_payload()]}])
        question = self._run(provider).questions[0]
        asset = question.metadata["asset"]
        self.assertIn("passage", asset)
        self.assertEqual(len(asset["questions"]), 8)
        self.assertEqual(question.metadata["subQuestionCount"], 8)

    def test_the_blueprint_constraints_reach_the_prompt(self):
        provider = _StubProvider([{"assets": [_reading_payload()]}])
        self._run(provider)
        prompt = provider.prompt_text()
        self.assertIn("350–450 words", prompt)
        self.assertIn("EXACTLY 8 sub-questions", prompt)
        self.assertIn("EXCEPT", prompt)  # the except_mcq skill gloss

    def test_no_chapter_text_can_reach_the_prompt(self):
        """Structural, not behavioural: `AssetRequest` has no field that could
        carry an upload, so there is no path by which one arrives."""
        self.assertNotIn(
            "chapter", {f.name for f in AssetRequest.__dataclass_fields__.values()}
        )

    def test_a_model_failure_degrades_to_a_reported_failure(self):
        class _Broken:
            def chat(self, request):
                raise RuntimeError("upstream is down")

        result = self._run(_Broken())
        self.assertEqual(result.questions, [])
        self.assertEqual(len(result.failures), 2)  # one per slot


class GrammarGeneratorTests(TestCase):
    def setUp(self):
        self.slot = _slot("grammar_task_set")

    def _run(self, provider, existing=()):
        generator = GrammarAssetGenerator()
        request = AssetRequest(
            slots=(self.slot,), subject="English", subject_norm="english",
            class_num=10, difficulty="medium", pool_id="p1", over_provision=2,
            existing=tuple(existing),
        )
        import services.assets.llm as llm

        original = llm.OpenAIProvider
        llm.OpenAIProvider = lambda: provider
        try:
            return generator.generate(request)
        finally:
            llm.OpenAIProvider = original

    def test_composes_task_sets_and_banks_the_atomic_tasks(self):
        topics = list(self.slot.constraints["grammar_topics"])
        provider = _StubProvider([{"tasks": _grammar_payload(topics * 2)}])
        result = self._run(provider)

        sets = [q for q in result.questions if q.asset_type == "grammar_task_set"]
        atoms = [q for q in result.questions if q.asset_type == "grammar_task"]

        self.assertEqual(len(sets), 2)  # main + OR alternative
        self.assertEqual(len(atoms), 24)  # the reusable pool
        for question in sets:
            self.assertEqual(question.marks, 10)
            self.assertIn("Complete any 10 of 12", question.question)
        for question in atoms:
            self.assertEqual(question.marks, 1)
            self.assertEqual(question.generator, "grammar_asset_pool")

    def test_each_set_covers_every_declared_grammar_topic_once(self):
        topics = list(self.slot.constraints["grammar_topics"])
        provider = _StubProvider([{"tasks": _grammar_payload(topics * 2)}])
        result = self._run(provider)

        for question in result.questions:
            if question.asset_type != "grammar_task_set":
                continue
            used = question.metadata["grammarTopics"]
            self.assertEqual(len(used), 12)
            self.assertEqual(len(set(used)), 12)

    def test_banked_tasks_reduce_what_has_to_be_written(self):
        topics = list(self.slot.constraints["grammar_topics"])
        banked = self._run(
            _StubProvider([{"tasks": _grammar_payload(topics * 2)}])
        ).questions
        atoms = [q for q in banked if q.asset_type == "grammar_task"]

        provider = _StubProvider([{"tasks": _grammar_payload(topics)}])
        result = self._run(provider, existing=atoms)

        # Everything it needed was already banked, so no new task was written.
        self.assertEqual(provider.requests, [])
        self.assertEqual(result.reused, len(atoms))
        self.assertEqual(
            len([q for q in result.questions if q.asset_type == "grammar_task_set"]), 2
        )


class WritingGeneratorTests(TestCase):
    def _run(self, slot, provider):
        generator = WritingAssetGenerator()
        request = AssetRequest(
            slots=(slot,), subject="English", subject_norm="english",
            class_num=10, difficulty="medium", pool_id="p1", over_provision=2,
        )
        import services.assets.llm as llm

        original = llm.OpenAIProvider
        llm.OpenAIProvider = lambda: provider
        try:
            return generator.generate(request)
        finally:
            llm.OpenAIProvider = original

    def test_the_internal_choice_gets_two_different_formats(self):
        slot = _slot("formal_letter_to_authority")
        provider = _StubProvider(
            [
                {
                    "assets": _writing_payload(
                        ["formal_letter_to_authority", "letter_to_editor",
                         "formal_letter_to_authority"]
                    )
                }
            ]
        )
        result = self._run(slot, provider)

        self.assertEqual(len(result.questions), 3)  # 2 alternates + the OR
        self.assertIn("letter_to_editor", {q.asset_type for q in result.questions})
        self.assertIn("`letter_to_editor`", provider.prompt_text())
        for question in result.questions:
            self.assertEqual(question.type, "LETTER")
            self.assertEqual(question.generator, "writing_asset_pool")

    def test_the_analytical_paragraph_asks_for_its_stimulus(self):
        slot = _slot("analytical_paragraph")
        provider = _StubProvider(
            [{"assets": _writing_payload(["analytical_paragraph"] * 3)}]
        )
        result = self._run(slot, provider)

        prompt = provider.prompt_text()
        self.assertIn("2 comparable stimulus blocks", prompt)
        self.assertIn("ONE cohesive paragraph", prompt)
        self.assertEqual(len(result.questions), 3)
        for question in result.questions:
            self.assertEqual(question.type, "ANALYTICAL_PARAGRAPH")
            self.assertEqual(question.metadata["stimulusBlocks"], 2)


class RunnerTests(TestCase):
    def test_runs_only_the_generators_the_plan_routes_to(self):
        plan = _english_plan()
        calls: Dict[str, int] = {}

        class _Recorder:
            def __init__(self, name):
                self.name = name
                self.label = name
                self.source_type = f"{name}_src"

            def generate(inner, request):  # noqa: N805
                calls[inner.name] = len(request.slots)
                from services.assets.base import AssetBatchResult

                return AssetBatchResult()

        import services.assets.runner as runner

        original = runner.get_generator
        runner.get_generator = lambda name: _Recorder(name)
        try:
            _, reports = generate_assets_for_plan(
                plan, subject="English", class_num=10, reuse=False
            )
        finally:
            runner.get_generator = original

        self.assertEqual(
            calls,
            {"reading_asset_pool": 2, "grammar_asset_pool": 1, "writing_asset_pool": 2},
        )
        self.assertNotIn(DEFAULT_GENERATOR, calls)
        self.assertEqual(len(reports), 3)

    def test_an_all_textbook_plan_does_no_asset_work(self):
        plan = list(
            build_question_plan(
                topic="Science", difficulty="medium", count=-1,
                class_num=10, subject="Science", count_variation="cbse",
            )
        )
        result, reports = generate_assets_for_plan(
            plan, subject="Science", class_num=10, reuse=False
        )
        self.assertEqual(result.questions, [])
        self.assertEqual(reports, [])
