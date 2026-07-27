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
    Extraction,
    build_message_history,
    can_generate,
    collect_source_ids,
    extract_spec,
    next_prompt,
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


class FollowUpTests(TestCase):
    def test_the_required_fields_are_asked_for_in_a_fixed_order(self):
        spec = {}
        asked = []
        for _ in range(4):
            prompt = next_prompt(spec)
            asked.append(prompt["field"])
            # Answer it and move on.
            spec[prompt["field"]] = prompt["options"][0]["value"]
        self.assertEqual(asked, ["subject", "academicClass", "board", "marks"])

    def test_options_are_closed_sets_the_generator_accepts(self):
        subject = next_prompt({})
        self.assertEqual(subject["kind"], "choice")
        self.assertIn(
            "Social Science", [o["label"] for o in subject["options"]]
        )
        # Ten classes, not eleven: the widget cannot offer a class the
        # blueprint engine has no pattern for.
        classes = next_prompt({"subject": "Science"})
        self.assertEqual(len(classes["options"]), 10)

    def test_sources_are_asked_for_before_the_optional_fields(self):
        spec = {
            "board": "CBSE",
            "academicClass": "10",
            "subject": "Science",
            "marks": "80",
        }
        prompt = next_prompt(spec, source_count=0)
        self.assertEqual(prompt["field"], "sources")
        # Not skippable: the generation endpoint rejects a request with no
        # sources, so a Skip here would build a button that fails on press.
        self.assertNotIn("optional", prompt)

    def test_an_attached_source_answers_the_files_prompt(self):
        spec = {
            "board": "CBSE",
            "academicClass": "10",
            "subject": "Science",
            "marks": "80",
        }
        self.assertEqual(
            next_prompt(spec, source_count=1)["field"], "difficulty"
        )

    def test_asking_runs_out(self):
        spec = {
            "board": "CBSE",
            "academicClass": "10",
            "subject": "Science",
            "marks": "80",
            "difficulty": "medium",
            "numberOfSets": "3",
        }
        self.assertIsNone(next_prompt(spec, source_count=1))

    def test_generating_needs_a_source_as_well_as_a_full_spec(self):
        spec = {
            "board": "CBSE",
            "academicClass": "10",
            "subject": "Science",
            "marks": "80",
        }
        # The blueprint is satisfied, but there is nothing to write from.
        self.assertTrue(spec_is_ready(spec))
        self.assertFalse(can_generate(spec, source_count=0))
        self.assertTrue(can_generate(spec, source_count=1))

    def test_sources_accumulate_across_the_whole_session(self):
        class _Message:
            def __init__(self, attachments):
                self.attachments = attachments

        messages = [
            _Message([{"id": "src-1", "name": "ch3.pdf"}]),
            _Message([]),
            _Message([{"id": "src-2", "name": "ch4.pdf"}, {"id": "src-1"}]),
            _Message(None),
        ]
        self.assertEqual(collect_source_ids(messages), ["src-1", "src-2"])


class ExtractionFailureTests(TestCase):
    def test_an_upstream_failure_keeps_the_previous_spec(self):
        previous = {"board": "CBSE", "marks": "80"}
        with patch("services.chat_service.get_openai_client", side_effect=RuntimeError("down")):
            self.assertEqual(extract_spec([], previous=previous).spec, previous)

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
            self.assertEqual(extract_spec([], previous=previous).spec, previous)


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
            return_value=Extraction(
                spec={
                    "board": "CBSE",
                    "academicClass": "10",
                    "subject": "Science",
                    "marks": "80",
                },
                is_paper=True,
            ),
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
        self.assertEqual(conversation.mode, Conversation.MODE_PAPER)
        self.assertEqual(
            [m.content for m in conversation.messages.all()],
            ["class 10 science, 80 marks, CBSE", "Sure thing."],
        )

        # The required fields are all in, so the widget offered next is the
        # first optional one rather than nothing at all.
        spec_block = next(
            b for b in body.split("\n\n") if b.startswith("event: spec")
        )
        payload = json.loads(spec_block.split("data: ", 1)[1])
        self.assertTrue(payload["ready"])
        # The blueprint is satisfied but nothing has been attached, so the
        # outstanding question is the source — and Generate stays shut.
        self.assertFalse(payload["canGenerate"])
        self.assertEqual(payload["nextPrompt"]["field"], "sources")

    def test_a_general_question_gets_no_paper_widget(self):
        conversation = Conversation.objects.create(user=self.user)

        with patch("apps.chat.views.keepalive", _no_keepalive), patch(
            "apps.chat.views.stream_reply", return_value=iter(["Photosynthesis is…"])
        ), patch(
            "apps.chat.views.extract_spec",
            return_value=Extraction(spec={}, is_paper=False),
        ):
            response = self.client.post(
                f"/api/chat/conversations/{conversation.id}/messages",
                {"content": "explain photosynthesis"},
                format="json",
            )
            body = b"".join(response.streaming_content).decode()

        spec_block = next(
            b for b in body.split("\n\n") if b.startswith("event: spec")
        )
        payload = json.loads(spec_block.split("data: ", 1)[1])
        self.assertIsNone(payload["nextPrompt"])
        self.assertEqual(payload["mode"], Conversation.MODE_CHAT)

        conversation.refresh_from_db()
        self.assertEqual(conversation.mode, Conversation.MODE_CHAT)


class SessionStatusTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(name="Teacher", email="t@example.com")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_a_session_can_be_paused_and_resumed(self):
        conversation = Conversation.objects.create(user=self.user)

        paused = self.client.post(
            f"/api/chat/conversations/{conversation.id}/status",
            {"status": "paused"},
            format="json",
        )
        self.assertEqual(paused.json()["status"], "paused")

        resumed = self.client.post(
            f"/api/chat/conversations/{conversation.id}/status",
            {"status": "active"},
            format="json",
        )
        self.assertEqual(resumed.json()["status"], "active")

    def test_completing_records_the_paper_it_produced(self):
        conversation = Conversation.objects.create(user=self.user)

        self.client.post(
            f"/api/chat/conversations/{conversation.id}/status",
            {"status": "completed", "paperId": "abc123"},
            format="json",
        )

        conversation.refresh_from_db()
        self.assertEqual(conversation.status, "completed")
        self.assertEqual(conversation.paper_id, "abc123")

    def test_an_unknown_status_is_rejected(self):
        conversation = Conversation.objects.create(user=self.user)
        response = self.client.post(
            f"/api/chat/conversations/{conversation.id}/status",
            {"status": "on fire"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_replying_to_a_paused_session_resumes_it(self):
        conversation = Conversation.objects.create(
            user=self.user, status=Conversation.STATUS_PAUSED
        )

        with patch("apps.chat.views.keepalive", _no_keepalive), patch(
            "apps.chat.views.stream_reply", return_value=iter(["ok"])
        ), patch(
            "apps.chat.views.extract_spec",
            return_value=Extraction(spec={"subject": "Science"}, is_paper=True),
        ):
            response = self.client.post(
                f"/api/chat/conversations/{conversation.id}/messages",
                {"content": "back to it"},
                format="json",
            )
            b"".join(response.streaming_content)

        conversation.refresh_from_db()
        self.assertEqual(conversation.status, Conversation.STATUS_ACTIVE)

    def test_a_resumed_session_carries_its_outstanding_question(self):
        conversation = Conversation.objects.create(
            user=self.user,
            mode=Conversation.MODE_PAPER,
            spec={"subject": "Science"},
        )
        detail = self.client.get(f"/api/chat/conversations/{conversation.id}").json()
        self.assertEqual(detail["next_prompt"]["field"], "academicClass")
        self.assertFalse(detail["ready"])

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
