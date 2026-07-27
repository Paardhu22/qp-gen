"""Chat assistant tests.

The model calls themselves are stubbed: what matters here is that a
conversation belongs to exactly one user, that the spec accumulates instead of
being overwritten each turn, and that a failed extraction cannot lose an
answer the teacher already gave.
"""

import json
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.chat.models import ChatMessage, Conversation
from services.chat_service import (
    build_message_history,
    extract_spec,
    normalize_spec,
    spec_is_ready,
    suggest_title,
)


class SpecNormalizationTests(TestCase):
    def test_a_later_turn_does_not_erase_an_earlier_answer(self):
        # Extraction sees the whole transcript, but a model that omits a field
        # it already agreed to must not blank it — the teacher would watch the
        # generate button disappear after answering one more question.
        previous = {"board": "CBSE", "academicClass": "10", "subject": "Science"}
        merged = normalize_spec({"marks": "80"}, previous)
        self.assertEqual(
            merged,
            {
                "board": "CBSE",
                "academicClass": "10",
                "subject": "Science",
                "marks": "80",
            },
        )

    def test_an_explicit_null_is_not_a_correction(self):
        previous = {"subject": "Science"}
        self.assertEqual(normalize_spec({"subject": None}, previous), previous)

    def test_a_changed_answer_wins(self):
        merged = normalize_spec({"subject": "Mathematics"}, {"subject": "Science"})
        self.assertEqual(merged["subject"], "Mathematics")

    def test_values_are_coerced_to_trimmed_strings(self):
        merged = normalize_spec({"marks": 80, "academicClass": "  10 "}, {})
        self.assertEqual(merged["marks"], "80")
        self.assertEqual(merged["academicClass"], "10")

    def test_chapters_survive_as_a_clean_list(self):
        merged = normalize_spec({"chapters": ["Light", "  ", "Electricity"]}, {})
        self.assertEqual(merged["chapters"], ["Light", "Electricity"])

    def test_junk_is_ignored_rather_than_raising(self):
        self.assertEqual(normalize_spec("not a dict", {"marks": "80"}), {"marks": "80"})

    def test_readiness_needs_all_four_required_fields(self):
        spec = {"board": "CBSE", "academicClass": "10", "subject": "Science"}
        self.assertFalse(spec_is_ready(spec))
        self.assertTrue(spec_is_ready({**spec, "marks": "80"}))
        self.assertFalse(spec_is_ready({**spec, "marks": "   "}))
        self.assertFalse(spec_is_ready(None))


class ExtractionFailureTests(TestCase):
    def test_an_upstream_failure_keeps_the_previous_spec(self):
        previous = {"board": "CBSE", "marks": "80"}
        with patch("services.chat_service.get_openai_client", side_effect=RuntimeError("down")):
            self.assertEqual(extract_spec([], previous=previous), previous)

    def test_unparseable_json_keeps_the_previous_spec(self):
        previous = {"board": "CBSE"}

        class _Message:
            content = "not json"

        class _Choice:
            message = _Message()

        class _Completion:
            choices = [_Choice()]
            usage = None

        class _Client:
            class chat:
                class completions:
                    @staticmethod
                    def create(**_kwargs):
                        return _Completion()

        with patch("services.chat_service.get_openai_client", return_value=_Client()):
            self.assertEqual(extract_spec([], previous=previous), previous)


class HistoryTests(TestCase):
    def test_the_system_prompt_leads_and_roles_are_filtered(self):
        history = build_message_history(
            [
                {"role": "user", "content": "class 10 science"},
                {"role": "tool", "content": "ignored"},
                {"role": "assistant", "content": "How many marks?"},
            ]
        )
        self.assertEqual(history[0]["role"], "system")
        self.assertEqual([m["role"] for m in history[1:]], ["user", "assistant"])

    def test_a_title_is_derived_without_a_model_call(self):
        self.assertEqual(suggest_title("  class 10   science  "), "class 10 science")
        self.assertTrue(suggest_title("x" * 200).endswith("…"))
        self.assertEqual(suggest_title(""), "New chat")


def _no_keepalive(stream):
    """Pass the stream through unwrapped.

    `keepalive` runs the generator on a worker thread so it can emit pings
    while the generator is blocked. That is exactly right in production and
    unusable here: the tests run on an in-memory SQLite database, and the
    generator's writes from a second thread hit `database table is locked`.
    The wrapper has its own suite in services/pool/test_keepalive.py; these
    tests are about what the view puts on the wire.
    """
    return stream


class ConversationApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(name="Teacher", email="t@example.com")
        self.other = User.objects.create(name="Other", email="o@example.com")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_a_conversation_is_created_and_listed(self):
        response = self.client.post("/api/chat/conversations", {}, format="json")
        self.assertEqual(response.status_code, 201)

        listing = self.client.get("/api/chat/conversations")
        self.assertEqual(len(listing.json()), 1)

    def test_another_users_conversation_is_not_reachable(self):
        theirs = Conversation.objects.create(user=self.other, title="Theirs")

        self.assertEqual(self.client.get(f"/api/chat/conversations/{theirs.id}").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/chat/conversations/{theirs.id}").status_code, 404)
        self.assertEqual(
            self.client.post(
                f"/api/chat/conversations/{theirs.id}/messages",
                {"content": "hello"},
                format="json",
            ).status_code,
            404,
        )
        self.assertTrue(Conversation.objects.filter(id=theirs.id).exists())

    def test_anonymous_access_is_rejected(self):
        anonymous = APIClient()
        self.assertIn(
            anonymous.get("/api/chat/conversations").status_code, (401, 403)
        )

    def test_messages_come_back_in_order(self):
        conversation = Conversation.objects.create(user=self.user)
        ChatMessage.objects.create(conversation=conversation, role="user", content="first")
        ChatMessage.objects.create(conversation=conversation, role="assistant", content="second")

        messages = self.client.get(f"/api/chat/conversations/{conversation.id}").json()["messages"]
        self.assertEqual([m["content"] for m in messages], ["first", "second"])

    def test_an_empty_message_with_no_attachment_is_rejected(self):
        conversation = Conversation.objects.create(user=self.user)
        response = self.client.post(
            f"/api/chat/conversations/{conversation.id}/messages",
            {"content": "   "},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_a_turn_streams_persists_and_titles_the_conversation(self):
        conversation = Conversation.objects.create(user=self.user)

        with patch(
            "apps.chat.views.keepalive", _no_keepalive
        ), patch(
            "apps.chat.views.stream_reply", return_value=iter(["Sure", " thing."])
        ), patch(
            "apps.chat.views.extract_spec",
            return_value={
                "board": "CBSE",
                "academicClass": "10",
                "subject": "Science",
                "marks": "80",
            },
        ):
            response = self.client.post(
                f"/api/chat/conversations/{conversation.id}/messages",
                {"content": "class 10 science, 80 marks, CBSE"},
                format="json",
            )
            body = b"".join(response.streaming_content).decode()

        self.assertIn('event: delta', body)
        self.assertIn('event: spec', body)
        self.assertIn('event: done', body)

        # Tokens keep their leading spaces: the frontend's SSE parser trims
        # each data line, so whitespace only survives inside the JSON string.
        deltas = [
            json.loads(block.split("data: ", 1)[1])["text"]
            for block in body.split("\n\n")
            if block.startswith("event: delta")
        ]
        self.assertEqual("".join(deltas), "Sure thing.")

        conversation.refresh_from_db()
        self.assertEqual(conversation.spec["marks"], "80")
        self.assertEqual(conversation.title, "class 10 science, 80 marks, CBSE")
        self.assertEqual(
            [m.content for m in conversation.messages.all()],
            ["class 10 science, 80 marks, CBSE", "Sure thing."],
        )

    def test_a_reply_that_dies_midway_still_persists_what_arrived(self):
        conversation = Conversation.objects.create(user=self.user)

        def _explode():
            yield "Partial"
            raise RuntimeError("upstream is down")

        with patch("apps.chat.views.keepalive", _no_keepalive), patch(
            "apps.chat.views.stream_reply", return_value=_explode()
        ):
            response = self.client.post(
                f"/api/chat/conversations/{conversation.id}/messages",
                {"content": "hello"},
                format="json",
            )
            body = b"".join(response.streaming_content).decode()

        self.assertIn("event: error", body)
        self.assertEqual(
            [m.content for m in conversation.messages.filter(role="assistant")],
            ["Partial"],
        )
