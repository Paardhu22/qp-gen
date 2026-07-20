"""Model 1 tests — pool generation from a chapter.

Everything downstream (auto-save, Model 2, the bank) trusts that Model 1 emits
well-formed, deduplicated PoolQuestions. These tests pin that contract against
the ways an LLM actually misbehaves: drifted type names, wrong option counts,
duplicate stems across parallel batches, and truncated responses.
"""

import json
from unittest.mock import patch

from django.test import TestCase, override_settings

from services.chapter_markdown import ChapterMarkdown
from services.pool.model1 import generate_question_pool
from services.pool.recipes import Batch, TypeQuota, batches_for_subject
from services.pool.schema import compute_content_hash
from services.pool.streaming import (
    JsonObjectStreamExtractor,
    parse_question_payload,
)

CHAPTER = ChapterMarkdown(
    markdown="# Electricity\n## Ohm's Law\n\nV = IR describes the relationship.",
    char_count=64,
)


def _mcq(index: int, **overrides):
    payload = {
        "topic": "Ohm's Law",
        "type": "MCQ",
        "blooms": "UNDERSTAND",
        "difficulty": "medium",
        "marks": 1,
        "question": f"Question number {index} about resistance?",
        "options": ["A one", "B two", "C three", "D four"],
        "answer": "A one",
        "explanation": "Because Ohm's law.",
    }
    payload.update(overrides)
    return payload


class StreamExtractorTests(TestCase):
    def test_extracts_objects_from_a_top_level_array(self):
        extractor = JsonObjectStreamExtractor()
        found = extractor.feed('[{"a": 1}, {"b": 2}]')
        self.assertEqual(found, [{"a": 1}, {"b": 2}])

    def test_objects_emit_incrementally_across_chunks(self):
        extractor = JsonObjectStreamExtractor()
        self.assertEqual(extractor.feed('[{"a": '), [])
        self.assertEqual(extractor.feed('1}'), [{"a": 1}])
        self.assertEqual(extractor.feed(', {"b"'), [])
        self.assertEqual(extractor.feed(': 2}]'), [{"b": 2}])

    def test_braces_inside_strings_do_not_break_depth(self):
        extractor = JsonObjectStreamExtractor()
        found = extractor.feed('[{"q": "the set {1, 2, 3} is finite"}]')
        self.assertEqual(found, [{"q": "the set {1, 2, 3} is finite"}])

    def test_escaped_quote_inside_string_is_handled(self):
        extractor = JsonObjectStreamExtractor()
        found = extractor.feed(r'[{"q": "he said \"hi\" loudly"}]')
        self.assertEqual(found, [{"q": 'he said "hi" loudly'}])

    def test_leading_markdown_fence_is_ignored(self):
        extractor = JsonObjectStreamExtractor()
        found = extractor.feed('```json\n[{"a": 1}]\n```')
        self.assertEqual(found, [{"a": 1}])

    def test_malformed_object_does_not_abort_the_batch(self):
        extractor = JsonObjectStreamExtractor()
        # Middle object has a trailing comma; the other two must survive.
        found = extractor.feed('[{"a": 1}, {"b": 2,}, {"c": 3}]')
        self.assertIn({"a": 1}, found)
        self.assertIn({"c": 3}, found)


class ParsePayloadFallbackTests(TestCase):
    def test_parses_bare_array(self):
        self.assertEqual(parse_question_payload('[{"a": 1}]'), [{"a": 1}])

    def test_unwraps_questions_key(self):
        self.assertEqual(
            parse_question_payload('{"questions": [{"a": 1}]}'), [{"a": 1}]
        )

    def test_salvages_complete_objects_from_a_truncated_response(self):
        truncated = '[{"a": 1}, {"b": 2}, {"c": '
        self.assertEqual(parse_question_payload(truncated), [{"a": 1}, {"b": 2}])

    def test_empty_input_returns_empty(self):
        self.assertEqual(parse_question_payload(""), [])


class RecipeTests(TestCase):
    def test_content_subject_pool_over_provisions_the_board_paper(self):
        batches = batches_for_subject("science")
        total = sum(b.total for b in batches)
        # A Class 10 board paper is 38 questions; the pool must offer real
        # choice, not a forced hand.
        self.assertGreaterEqual(total, 76)

    def test_language_subject_gets_a_different_mix(self):
        science_types = {
            q.type for b in batches_for_subject("science") for q in b.quotas
        }
        english_types = {
            q.type for b in batches_for_subject("english") for q in b.quotas
        }
        self.assertIn("GRAMMAR", english_types)
        self.assertNotIn("GRAMMAR", science_types)

    def test_target_total_rescales_but_keeps_the_mix(self):
        full = batches_for_subject("science")
        small = batches_for_subject("science", target_total=40)

        self.assertLess(sum(b.total for b in small), sum(b.total for b in full))
        self.assertEqual(
            {q.type for b in full for q in b.quotas},
            {q.type for b in small for q in b.quotas},
            "Rescaling must not drop a question type entirely.",
        )

    def test_output_budget_scales_with_the_heaviest_shape(self):
        case_batch = Batch("case", [TypeQuota("CASE_STUDY", 4, 6)])
        mcq_batch = Batch("obj", [TypeQuota("MCQ", 1, 6)])
        self.assertGreater(case_batch.max_output_tokens, mcq_batch.max_output_tokens)


def _batch_name_of(request) -> str:
    """Recover which batch a request belongs to from its operation label."""
    return request.operation.replace("pool_model1_", "")


class _FakeProvider:
    """Scripted provider.

    Dispatches on BATCH NAME rather than call order, because batches run
    concurrently and retry — call order is neither stable nor meaningful.
    `responder` maps a batch name to a payload (list of dicts, a raw string, or
    an Exception to raise).
    """

    def __init__(self, responder):
        self._responder = responder
        self.requests = []

    def stream_chat(self, request):
        self.requests.append(request)
        payload = self._responder(_batch_name_of(request), len(self.requests))
        if isinstance(payload, Exception):
            raise payload
        # Emit in small slices so incremental parsing is genuinely exercised.
        text = payload if isinstance(payload, str) else json.dumps(payload)
        for i in range(0, len(text), 17):
            yield text[i : i + 17]


def _distinct_per_batch(count=5):
    """Each batch returns its own distinct questions — the normal case."""

    def responder(batch_name, _call_index):
        return [
            _mcq(i, question=f"{batch_name} question {i} about resistance?")
            for i in range(count)
        ]

    return responder


def _same_for_every_batch(payload):
    def responder(_batch_name, _call_index):
        return payload

    return responder


class GeneratePoolTests(TestCase):
    def _run(self, responder, **kwargs):
        provider = _FakeProvider(responder)
        with patch("services.pool.model1.OpenAIProvider", return_value=provider):
            result = generate_question_pool(
                chapter=CHAPTER,
                subject="Science",
                subject_norm="science",
                chapter_name="Electricity",
                class_num=10,
                **kwargs,
            )
        return result, provider

    def test_empty_chapter_short_circuits_without_calling_the_model(self):
        provider = _FakeProvider(_distinct_per_batch())
        with patch("services.pool.model1.OpenAIProvider", return_value=provider):
            result = generate_question_pool(
                chapter=ChapterMarkdown(markdown=""),
                subject="Science",
                subject_norm="science",
                chapter_name="Electricity",
                class_num=10,
            )
        self.assertEqual(result.total, 0)
        self.assertEqual(provider.requests, [])
        self.assertTrue(result.batch_failures)

    def test_questions_are_collected_across_batches(self):
        result, provider = self._run(_distinct_per_batch(count=5))
        # Four batches in the science recipe, each contributing 5 distinct
        # questions.
        self.assertEqual(len(provider.requests), 4)
        self.assertEqual(result.total, 20)
        self.assertEqual(result.batch_failures, [])

    def test_duplicate_stems_across_batches_are_dropped(self):
        # Every batch returns the SAME three questions.
        result, _ = self._run(_same_for_every_batch([_mcq(1), _mcq(2), _mcq(3)]))
        self.assertEqual(result.total, 3, "Only the first batch's copies survive.")
        self.assertEqual(result.duplicates_dropped, 9)

    def test_malformed_questions_are_dropped_not_fatal(self):
        payload = [
            _mcq(1),
            _mcq(2, options=["only", "three", "options"]),  # MCQ needs exactly 4
            _mcq(3, type="NOT_A_REAL_TYPE"),
            _mcq(4, question=""),
            _mcq(5),
        ]
        result, _ = self._run(_same_for_every_batch(payload))
        # 2 good per batch × 4 batches, deduped to 2 distinct stems.
        self.assertEqual(result.total, 2)
        self.assertGreater(result.invalid_dropped, 0)

    def test_type_aliases_are_normalised(self):
        result, _ = self._run(_same_for_every_batch([_mcq(1, type="multiple choice")]))
        self.assertEqual(result.total, 1)
        self.assertEqual(result.questions[0].type, "MCQ")

    def test_assertion_reason_gets_canonical_options(self):
        payload = [
            {
                "topic": "Ohm's Law",
                "type": "ASSERTION_REASON",
                "blooms": "ANALYZE",
                "difficulty": "medium",
                "marks": 1,
                "question": "Assertion (A): ... Reason (R): ...",
                "options": ["the model's own paraphrase"],
                "answer": "(a)",
                "explanation": "why",
            }
        ]
        result, _ = self._run(_same_for_every_batch(payload))
        self.assertEqual(result.total, 1)
        options = result.questions[0].options
        self.assertEqual(len(options), 4)
        self.assertIn("correct explanation", options[0])

    def test_a_permanently_failing_batch_is_isolated_and_reported(self):
        distinct = _distinct_per_batch(count=3)

        def responder(batch_name, call_index):
            if batch_name == "objective":
                raise_me = RuntimeError("provider exploded")
                return raise_me
            return distinct(batch_name, call_index)

        result, provider = self._run(responder)

        # The objective batch exhausts its retries and is reported...
        self.assertTrue(
            any("objective" in f for f in result.batch_failures),
            f"expected an objective-batch failure, got {result.batch_failures}",
        )
        # ...while the other three still deliver their questions.
        self.assertEqual(result.total, 9)

    def test_a_batch_that_fails_once_recovers_on_retry(self):
        distinct = _distinct_per_batch(count=3)
        attempts = {"objective": 0}

        def responder(batch_name, call_index):
            if batch_name == "objective":
                attempts["objective"] += 1
                if attempts["objective"] == 1:
                    return RuntimeError("transient blip")
            return distinct(batch_name, call_index)

        result, _ = self._run(responder)

        self.assertEqual(result.batch_failures, [])
        self.assertEqual(result.total, 12, "All four batches ultimately deliver.")

    def test_on_question_fires_once_per_accepted_question(self):
        seen = []
        result, _ = self._run(_distinct_per_batch(count=2), on_question=seen.append)
        self.assertEqual(len(seen), result.total)
        self.assertEqual({q.id for q in seen}, {q.id for q in result.questions})

    def test_on_question_does_not_fire_for_duplicates(self):
        seen = []
        result, _ = self._run(
            _same_for_every_batch([_mcq(1), _mcq(2)]), on_question=seen.append
        )
        self.assertEqual(len(seen), 2)
        self.assertEqual(result.duplicates_dropped, 6)

    def test_every_question_carries_pool_and_chapter_metadata(self):
        result, _ = self._run(_same_for_every_batch([_mcq(1)]))
        question = result.questions[0]
        self.assertEqual(question.pool_id, result.pool_id)
        self.assertEqual(question.chapter, "Electricity")
        self.assertEqual(question.subject, "Science")
        self.assertEqual(
            question.content_hash,
            compute_content_hash("Science", "Electricity", question.question),
        )

    def test_chapter_precedes_the_batch_instruction_for_prefix_caching(self):
        _, provider = self._run(_same_for_every_batch([_mcq(1)]))
        messages = provider.requests[0].messages
        self.assertIn("CHAPTER SOURCE MATERIAL", str(messages[1].content))
        self.assertIn("Write exactly", str(messages[2].content))

    def test_batch_output_budget_reaches_the_request(self):
        _, provider = self._run(_same_for_every_batch([_mcq(1)]))
        for request in provider.requests:
            self.assertIsNotNone(request.max_output_tokens)
            self.assertGreater(request.max_output_tokens, 0)

    def test_usage_is_attributed_to_an_operation(self):
        _, provider = self._run(_same_for_every_batch([_mcq(1)]))
        operations = {r.operation for r in provider.requests}
        self.assertTrue(all(op.startswith("pool_model1_") for op in operations))
        self.assertEqual(len(operations), 4, "Each batch costs separately.")
