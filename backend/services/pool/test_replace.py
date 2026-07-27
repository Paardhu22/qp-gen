"""Per-question replacement — one slot changes, nothing else does.

The property under test is narrow and unforgiving: a replacement must be
eligible for the SAME blueprint slot (marks, type, generator), must not be a
question already on the paper, and must not cost a model call when the bank can
answer. The pool over-provisions every slot roughly 2×, so the bank almost
always can.
"""

from unittest.mock import patch

from django.test import TestCase

from apps.accounts.models import User
from apps.projects.models import Question
from services.pool import store
from services.pool.replace import (
    ReplacementError,
    ReplacementSlot,
    build_slot,
    replace_question,
)
from services.pool.schema import PoolQuestion, compute_content_hash, slot_accepts


def _question(qid, *, qtype="SHORT_ANSWER", marks=3, chapter="The Thief's Story",
              topic=None, generator="question_pool", asset_type="",
              subject="English", text=None):
    body = text or f"{qtype} {marks}m #{qid} about the chapter?"
    return PoolQuestion(
        id=qid, subject=subject, chapter=chapter, topic=topic or f"topic-{qid}",
        type=qtype, blooms="UNDERSTAND", difficulty="medium", marks=marks,
        question=body, answer="an answer", explanation="because",
        generator=generator, asset_type=asset_type,
        source_type="reading_asset" if generator != "question_pool" else "pool",
        content_hash=compute_content_hash(subject, chapter, body),
    )


def _spec(**overrides):
    spec = {
        "slotIndex": 8,
        "section": "Section C - Literature Textbook",
        "marks": 3,
        "type": "SHORT_ANSWER",
        "generator": "question_pool",
        "assetType": "",
        "chapter": "The Thief's Story",
        "topic": "topic-a",
        "difficulty": "medium",
        "subject": "English",
        "classNum": 10,
        "questionId": "a",
    }
    spec.update(overrides)
    return spec


class SlotReconstructionTests(TestCase):
    def test_the_slot_keeps_everything_that_defines_it(self):
        slot = build_slot(_spec())
        self.assertEqual(slot.marks, 3)
        self.assertEqual(slot.question_type, "SHORT_ANSWER")
        self.assertEqual(slot.legacy_type, "SHORT")
        self.assertEqual(slot.section_title, "Section C - Literature Textbook")
        self.assertEqual(slot.generator, "question_pool")
        self.assertEqual(slot.chapter, "The Thief's Story")

    def test_asset_slots_keep_their_generator_and_asset_type(self):
        slot = build_slot(
            _spec(
                generator="reading_asset_pool",
                assetType="discursive_passage",
                type="READING_COMP",
                marks=10,
            )
        )
        self.assertEqual(slot.generator, "reading_asset_pool")
        self.assertEqual(slot.asset_type, "discursive_passage")
        self.assertEqual(slot.legacy_type, "CASE_STUDY")

    def test_a_reconstructed_slot_works_with_the_real_eligibility_check(self):
        """`slot_accepts` is the assembler's own predicate — a replacement is
        eligible in exactly the sense the paper requires, not a parallel one."""
        slot = build_slot(_spec())
        self.assertTrue(slot_accepts(_question("x"), slot))
        self.assertFalse(slot_accepts(_question("x", marks=5), slot))
        self.assertFalse(
            slot_accepts(_question("x", generator="reading_asset_pool"), slot)
        )


class ReplaceFromBankTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            id="replace00000000000000000000001", name="R", email="r@test.local"
        )
        store.persist_pool(
            user=self.user,
            questions=[_question(chr(97 + i)) for i in range(5)],
            subject="English",
            chapter="The Thief's Story",
            class_num=10,
        )

    def test_a_replacement_comes_from_the_bank_without_a_model_call(self):
        with patch("services.pool.replace._generate_textbook") as generate:
            result = replace_question(user=self.user, spec=_spec())
        generate.assert_not_called()
        self.assertEqual(result.source, "bank")
        self.assertEqual(result.question.marks, 3)
        self.assertEqual(result.question.type, "SHORT_ANSWER")

    def test_questions_already_on_the_paper_are_never_offered(self):
        rows = list(Question.objects.filter(user=self.user))
        keep = [r.id for r in rows[:4]]
        result = replace_question(user=self.user, spec=_spec(), exclude_ids=keep)
        self.assertNotIn(result.question.id, keep)

    def test_the_slot_marks_are_preserved(self):
        store.persist_pool(
            user=self.user,
            questions=[_question("big", marks=6, text="A six mark question?")],
            subject="English",
            chapter="The Thief's Story",
            class_num=10,
        )
        for _ in range(5):
            result = replace_question(user=self.user, spec=_spec())
            self.assertEqual(result.question.marks, 3)

    def test_a_textbook_slot_never_draws_an_asset_question(self):
        store.persist_pool(
            user=self.user,
            questions=[
                _question(
                    "asset",
                    generator="reading_asset_pool",
                    asset_type="discursive_passage",
                    chapter="Reading Skills — Unseen Passages",
                    text="An unseen passage question?",
                )
            ],
            subject="English",
            chapter="Reading Skills — Unseen Passages",
            class_num=10,
        )
        for _ in range(5):
            result = replace_question(user=self.user, spec=_spec())
            self.assertEqual(result.question.generator, "question_pool")

    def test_bank_only_mode_fails_cleanly_when_nothing_is_left(self):
        every_id = [r.id for r in Question.objects.filter(user=self.user)]
        with self.assertRaises(ReplacementError):
            replace_question(
                user=self.user,
                spec=_spec(),
                exclude_ids=every_id,
                allow_generation=False,
            )

    def test_a_chapter_with_nothing_left_widens_to_the_whole_subject(self):
        """A teacher who uploaded several chapters wants a replacement from
        any of them rather than no replacement at all."""
        store.persist_pool(
            user=self.user,
            questions=[_question("other", chapter="Bholi", text="A Bholi question?")],
            subject="English",
            chapter="Bholi",
            class_num=10,
        )
        used = [
            r.id
            for r in Question.objects.filter(
                user=self.user, inferred_chapter="The Thief's Story"
            )
        ]
        result = replace_question(user=self.user, spec=_spec(), exclude_ids=used)
        self.assertEqual(result.question.chapter, "Bholi")


class ReplaceByGeneratingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            id="replace00000000000000000000002", name="G", email="g@test.local"
        )

    def test_an_asset_slot_calls_its_own_generator_for_one_slot(self):
        captured = {}

        class _FakeGenerator:
            name = "reading_asset_pool"
            label = "Reading"
            source_type = "reading_asset"

            def generate(self, request):
                from services.assets.base import AssetBatchResult

                captured["slots"] = list(request.slots)
                captured["over_provision"] = request.over_provision
                return AssetBatchResult(
                    questions=[
                        _question(
                            "fresh",
                            qtype="READING_COMP",
                            marks=10,
                            generator="reading_asset_pool",
                            asset_type="discursive_passage",
                            chapter="Reading Skills — Unseen Passages",
                            text="A brand new unseen passage?",
                        )
                    ]
                )

        with patch(
            "services.assets.registry.get_generator", return_value=_FakeGenerator()
        ):
            result = replace_question(
                user=self.user,
                spec=_spec(
                    generator="reading_asset_pool",
                    assetType="discursive_passage",
                    type="READING_COMP",
                    marks=10,
                ),
            )

        self.assertEqual(result.source, "generated")
        self.assertEqual(len(captured["slots"]), 1)
        self.assertIsInstance(captured["slots"][0], ReplacementSlot)
        # One replacement, one candidate — a second is pure cost.
        self.assertEqual(captured["over_provision"], 1)

    def test_a_generated_replacement_is_banked_for_next_time(self):
        class _FakeGenerator:
            name = "reading_asset_pool"
            label = "Reading"
            source_type = "reading_asset"

            def generate(self, request):
                from services.assets.base import AssetBatchResult

                return AssetBatchResult(
                    questions=[
                        _question(
                            "fresh",
                            qtype="READING_COMP",
                            marks=10,
                            generator="reading_asset_pool",
                            asset_type="discursive_passage",
                            chapter="Reading Skills — Unseen Passages",
                            text="A brand new unseen passage?",
                        )
                    ]
                )

        with patch(
            "services.assets.registry.get_generator", return_value=_FakeGenerator()
        ):
            replace_question(
                user=self.user,
                spec=_spec(
                    generator="reading_asset_pool",
                    assetType="discursive_passage",
                    type="READING_COMP",
                    marks=10,
                ),
            )

        self.assertTrue(
            Question.objects.filter(
                user=self.user, source_type="reading_asset"
            ).exists()
        )

    def test_a_generator_that_returns_nothing_usable_raises(self):
        class _Empty:
            name = "reading_asset_pool"
            label = "Reading"
            source_type = "reading_asset"

            def generate(self, request):
                from services.assets.base import AssetBatchResult

                return AssetBatchResult()

        with patch("services.assets.registry.get_generator", return_value=_Empty()):
            with self.assertRaises(ReplacementError):
                replace_question(
                    user=self.user,
                    spec=_spec(
                        generator="reading_asset_pool",
                        type="READING_COMP",
                        marks=10,
                    ),
                )


class ReplaceEndpointTests(TestCase):
    """The HTTP contract the editor and review workspace both call."""

    def setUp(self):
        self.user = User.objects.create(
            id="replace00000000000000000000003", name="E", email="e@test.local"
        )
        store.persist_pool(
            user=self.user,
            questions=[_question(chr(97 + i)) for i in range(4)],
            subject="English",
            chapter="The Thief's Story",
            class_num=10,
        )

    def _post(self, payload):
        from apps.generation.views import ReplaceQuestionView
        from rest_framework.test import APIRequestFactory, force_authenticate

        request = APIRequestFactory().post(
            "/api/generation/replace-question", payload, format="json"
        )
        force_authenticate(request, user=self.user)
        return ReplaceQuestionView.as_view()(request)

    def test_returns_a_question_in_the_shape_the_editor_inserts(self):
        response = self._post({"slot": _spec()})
        self.assertEqual(response.status_code, 200)

        question = response.data["question"]
        for field in ("content", "type", "options", "answer", "marks", "metadata"):
            self.assertIn(field, question)
        self.assertEqual(question["marks"], 3)
        self.assertEqual(question["metadata"]["slotIndex"], 8)
        self.assertEqual(
            question["metadata"]["section"], "Section C - Literature Textbook"
        )
        self.assertEqual(question["metadata"]["generator"], "question_pool")

    def test_exhausting_the_bank_without_generation_is_a_409(self):
        every_id = [r.id for r in Question.objects.filter(user=self.user)]
        response = self._post(
            {"slot": _spec(), "excludeIds": every_id, "allowGeneration": False}
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("error", response.data)

    def test_marks_and_type_are_required(self):
        response = self._post({"slot": {"section": "Section A"}})
        self.assertEqual(response.status_code, 400)
