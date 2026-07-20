"""Image-question stage tests.

The image API is mocked throughout — these tests must never issue a real
gpt-image-1 call, which costs money and takes 10-20s.

The behaviours worth pinning: the strategy knob actually switches paths,
prompt-hash caching prevents paying twice for one diagram, synthesised
questions are tagged for teacher review, and a failing image stage degrades
without taking the text pool with it.
"""

import base64
import json
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from services.chapter_markdown import ChapterMarkdown, Figure
from services.pool.image_model import (
    generate_image_questions,
    resolve_strategy,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-image-payload"
PNG_B64 = base64.b64encode(PNG_BYTES).decode("ascii")

CHAPTER = ChapterMarkdown(
    markdown="# Electricity\n## Circuits\n\nA series circuit has one path.",
    char_count=60,
    figures=[
        Figure(
            url="/media/pdf_images/src/page-3-image-1.png",
            caption="A series circuit containing a cell, a resistor and an ammeter.",
            page=3,
            source_pdf="electricity.pdf",
        ),
        Figure(
            url="/media/pdf_images/src/page-5-image-1.png",
            caption="A parallel circuit with two resistors across a battery.",
            page=5,
            source_pdf="electricity.pdf",
        ),
    ],
)

SPEC = {
    "topic": "Series circuits",
    "diagram_prompt": "A black and white textbook diagram of a series circuit "
                      "with a cell on the left, a resistor on top, an ammeter "
                      "on the right, connected by straight wires.",
    "type": "DIAGRAM",
    "blooms": "UNDERSTAND",
    "difficulty": "medium",
    "marks": 2,
    "question": "In the given figure, identify the component that measures current.",
    "options": [],
    "answer": "The ammeter.",
    "explanation": "An ammeter is connected in series to measure current.",
}

REUSE_QUESTION = {
    "figure_number": 1,
    "topic": "Series circuits",
    "type": "DIAGRAM",
    "blooms": "UNDERSTAND",
    "difficulty": "medium",
    "marks": 2,
    "question": "In the given figure, name the component connected in series.",
    "options": [],
    "answer": "The ammeter.",
    "explanation": "It is in the single current path.",
}


class _FakeProvider:
    """Returns a scripted JSON payload, sliced to exercise buffering."""

    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def stream_chat(self, request):
        self.requests.append(request)
        if isinstance(self.payload, Exception):
            raise self.payload
        text = json.dumps(self.payload)
        for i in range(0, len(text), 23):
            yield text[i : i + 23]


def _fake_image_response(b64=PNG_B64):
    response = MagicMock()
    datum = MagicMock()
    datum.b64_json = b64
    datum.url = None
    response.data = [datum]
    return response


class StrategyResolutionTests(TestCase):
    @override_settings(IMAGE_QUESTION_STRATEGY="reuse")
    def test_reads_the_setting(self):
        self.assertEqual(resolve_strategy(), "reuse")

    @override_settings(IMAGE_QUESTION_STRATEGY="nonsense")
    def test_unknown_strategy_falls_back_to_generate(self):
        self.assertEqual(resolve_strategy(), "generate")


class _ImageStageTestCase(TestCase):
    def _run(self, *, payload, strategy, images_exist=False, image_side_effect=None, **kwargs):
        provider = _FakeProvider(payload)
        client = MagicMock()
        client.images.generate.side_effect = image_side_effect or (
            lambda **_: _fake_image_response()
        )

        saved = {}

        def _save(path, content):
            saved[path] = content.read()
            return path

        with patch("services.pool.image_model.OpenAIProvider", return_value=provider), \
             patch("services.pool.image_model.get_openai_client", return_value=client), \
             patch("services.pool.image_model.default_storage") as storage:
            storage.exists.return_value = images_exist
            storage.save.side_effect = _save
            result = generate_image_questions(
                chapter=CHAPTER,
                subject="Science",
                chapter_name="Electricity",
                class_num=10,
                pool_id="pool123",
                strategy=strategy,
                **kwargs,
            )
        return result, client, provider, saved


@override_settings(IMAGE_COST_USD_PER_IMAGE=0.04)
class GenerateStrategyTests(_ImageStageTestCase):
    def test_draws_a_diagram_and_attaches_it_to_the_question(self):
        result, client, _, saved = self._run(
            payload=[SPEC], strategy="generate", count=1
        )

        self.assertEqual(result.total, 1)
        self.assertEqual(client.images.generate.call_count, 1)
        self.assertEqual(len(saved), 1)

        question = result.questions[0]
        self.assertTrue(question.image)
        self.assertIn("generated_diagrams/", question.image)
        self.assertEqual(question.type, "DIAGRAM")

    def test_synthesised_questions_are_tagged_for_teacher_review(self):
        result, _, _, _ = self._run(payload=[SPEC], strategy="generate", count=1)
        question = result.questions[0]

        self.assertEqual(question.source_type, "synthetic_image")
        self.assertTrue(question.metadata["syntheticImage"])
        self.assertTrue(question.metadata["requiresReview"])
        self.assertEqual(question.metadata["imagePrompt"], SPEC["diagram_prompt"])

    def test_cached_diagram_is_not_regenerated(self):
        result, client, _, saved = self._run(
            payload=[SPEC], strategy="generate", count=1, images_exist=True
        )

        self.assertEqual(result.total, 1)
        self.assertEqual(client.images.generate.call_count, 0, "Cache hit must not bill.")
        self.assertEqual(saved, {})
        self.assertEqual(result.cache_hits, 1)
        self.assertEqual(result.generated_count, 0)
        self.assertEqual(result.estimated_cost_usd, 0.0)

    def test_cost_is_estimated_per_generated_image(self):
        specs = [
            dict(SPEC, question=f"Question {i}?", diagram_prompt=f"Diagram {i}")
            for i in range(3)
        ]
        result, _, _, _ = self._run(payload=specs, strategy="generate", count=3)

        self.assertEqual(result.generated_count, 3)
        self.assertAlmostEqual(result.estimated_cost_usd, 0.12, places=4)

    def test_count_caps_how_many_diagrams_are_drawn(self):
        specs = [
            dict(SPEC, question=f"Question {i}?", diagram_prompt=f"Diagram {i}")
            for i in range(10)
        ]
        result, client, _, _ = self._run(payload=specs, strategy="generate", count=2)

        self.assertEqual(client.images.generate.call_count, 2)
        self.assertEqual(result.total, 2)

    def test_image_failure_drops_the_question_not_the_stage(self):
        specs = [
            dict(SPEC, question="Good one?", diagram_prompt="Diagram A"),
            dict(SPEC, question="Bad one?", diagram_prompt="Diagram B"),
        ]

        def flaky(**kwargs):
            if kwargs.get("prompt") == "Diagram B":
                raise RuntimeError("content policy rejection")
            return _fake_image_response()

        result, _, _, _ = self._run(
            payload=specs, strategy="generate", count=2, image_side_effect=flaky
        )

        self.assertEqual(result.total, 1)
        self.assertEqual(result.questions[0].question, "Good one?")
        self.assertTrue(result.failures)

    def test_spec_call_failure_is_contained(self):
        result, client, _, _ = self._run(
            payload=RuntimeError("spec model down"), strategy="generate", count=2
        )
        self.assertEqual(result.total, 0)
        self.assertTrue(result.failures)
        self.assertEqual(client.images.generate.call_count, 0)

    def test_specs_without_a_diagram_prompt_are_skipped(self):
        result, client, _, _ = self._run(
            payload=[dict(SPEC, diagram_prompt="")], strategy="generate", count=1
        )
        self.assertEqual(result.total, 0)
        self.assertEqual(client.images.generate.call_count, 0)


class ReuseStrategyTests(_ImageStageTestCase):
    def test_attaches_the_real_chapter_figure_and_never_bills_the_image_api(self):
        result, client, _, _ = self._run(
            payload=[REUSE_QUESTION], strategy="reuse", count=2
        )

        self.assertEqual(result.total, 1)
        self.assertEqual(client.images.generate.call_count, 0)

        question = result.questions[0]
        self.assertEqual(question.image, CHAPTER.figures[0].url)
        self.assertEqual(question.source_type, "chapter_figure")
        self.assertFalse(question.metadata["syntheticImage"])
        self.assertEqual(result.estimated_cost_usd, 0.0)

    def test_out_of_range_figure_number_is_rejected(self):
        result, _, _, _ = self._run(
            payload=[dict(REUSE_QUESTION, figure_number=99)],
            strategy="reuse", count=2,
        )
        self.assertEqual(result.total, 0)

    def test_chapter_without_usable_figures_produces_nothing(self):
        provider = _FakeProvider([REUSE_QUESTION])
        with patch("services.pool.image_model.OpenAIProvider", return_value=provider):
            result = generate_image_questions(
                chapter=ChapterMarkdown(markdown="# C\n\nNo figures here.", char_count=20),
                subject="Science", chapter_name="Electricity", class_num=10,
                pool_id="p", strategy="reuse", count=3,
            )
        self.assertEqual(result.total, 0)
        self.assertEqual(provider.requests, [], "No figures means no authoring call.")


class HybridStrategyTests(_ImageStageTestCase):
    def test_reuses_first_then_synthesises_the_remainder(self):
        # The chapter offers 2 figures; ask for 3. Reuse should cover 1 (the
        # scripted response only names figure 1), generation covers the rest.
        provider = _FakeProvider([REUSE_QUESTION])
        client = MagicMock()
        client.images.generate.side_effect = lambda **_: _fake_image_response()

        # Reuse and generate call the provider in turn; give the second call a
        # spec payload by swapping the provider's script after the first use.
        class _TwoPhaseProvider:
            def __init__(self):
                self.calls = 0
                self.requests = []

            def stream_chat(self, request):
                self.requests.append(request)
                self.calls += 1
                payload = [REUSE_QUESTION] if request.operation == "pool_image_reuse" else [
                    dict(SPEC, question="Synth one?", diagram_prompt="Diagram S1"),
                    dict(SPEC, question="Synth two?", diagram_prompt="Diagram S2"),
                ]
                text = json.dumps(payload)
                for i in range(0, len(text), 23):
                    yield text[i : i + 23]

        provider = _TwoPhaseProvider()
        with patch("services.pool.image_model.OpenAIProvider", return_value=provider), \
             patch("services.pool.image_model.get_openai_client", return_value=client), \
             patch("services.pool.image_model.default_storage") as storage:
            storage.exists.return_value = False
            storage.save.side_effect = lambda path, content: path
            result = generate_image_questions(
                chapter=CHAPTER, subject="Science", chapter_name="Electricity",
                class_num=10, pool_id="p", strategy="hybrid", count=3,
            )

        self.assertEqual(result.reused_count, 1)
        self.assertEqual(result.generated_count, 2)
        self.assertEqual(result.total, 3)
        # Only the shortfall was drawn, not all three.
        self.assertEqual(client.images.generate.call_count, 2)


class CapAndDegradationTests(_ImageStageTestCase):
    @override_settings(IMAGE_QUESTIONS_PER_POOL=0)
    def test_zero_cap_disables_the_stage_entirely(self):
        provider = _FakeProvider([SPEC])
        with patch("services.pool.image_model.OpenAIProvider", return_value=provider):
            result = generate_image_questions(
                chapter=CHAPTER, subject="Science", chapter_name="Electricity",
                class_num=10, pool_id="p",
            )
        self.assertEqual(result.total, 0)
        self.assertEqual(provider.requests, [])

    def test_empty_chapter_produces_nothing(self):
        provider = _FakeProvider([SPEC])
        with patch("services.pool.image_model.OpenAIProvider", return_value=provider):
            result = generate_image_questions(
                chapter=ChapterMarkdown(markdown=""), subject="Science",
                chapter_name="Electricity", class_num=10, pool_id="p", count=3,
            )
        self.assertEqual(result.total, 0)
        self.assertTrue(result.failures)
