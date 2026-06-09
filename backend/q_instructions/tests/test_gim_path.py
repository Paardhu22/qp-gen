"""General Instructions Mode (GIM) regression tests.

GIM ran through a code path that built a `dict` LLM request and passed
it to `OpenAIProvider.stream_chat`, which accesses attributes
(`request.model`, `request.messages`). Every slot raised
``AttributeError`` before reaching OpenAI, surfacing as the catch-all
"Generation failed before any questions could be produced" error.

These tests pin the contract:

1. The request object passed to the provider is the dataclass
   ``LLMRequest`` (not a dict). If a future refactor regresses to a
   dict, the provider's attribute access will fail and this test will
   too.
2. With a stubbed provider returning valid JSON, a two-section
   instruction string produces real question objects per section.
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
from dotenv import load_dotenv
load_dotenv(
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        ".env",
    )
)
django.setup()

import json  # noqa: E402

from apps.question_generation.infrastructure.providers.base import LLMRequest  # noqa: E402


def _collect_sse(generator):
    """Drain an SSE generator into a list of (event_name, payload) tuples."""
    events = []
    for chunk in generator:
        if not chunk:
            continue
        event_name = None
        data_lines = []
        for line in chunk.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: "):]
            elif line.startswith("data: "):
                data_lines.append(line[len("data: "):])
        if data_lines:
            try:
                payload = json.loads("\n".join(data_lines))
            except json.JSONDecodeError:
                payload = {"_raw": "\n".join(data_lines)}
            events.append((event_name or "message", payload))
    return events


class _CannedProvider:
    """OpenAIProvider stand-in. Yields a canned JSON object per call so we
    can drive `stream_general_instructions_questions` end-to-end without
    hitting OpenAI."""

    def __init__(self):
        self.requests = []
        self._counter = 0

    def stream_chat(self, request):
        # If GIM ever regresses to passing a dict again, this will raise
        # AttributeError exactly like the real provider would.
        self.requests.append({
            "model": request.model,
            "system_role": request.messages[0].role,
            "user_role": request.messages[1].role,
            "response_format": request.response_format,
            "stream": request.stream,
        })
        self._counter += 1
        canned = {
            "question": {
                "content": f"Stub question #{self._counter}",
                "type": "SHORT_ANSWER",
                "answer": "Stub answer",
                "marks": 2,
            }
        }
        for ch in json.dumps(canned):
            yield ch


class GimRequestContractTests(unittest.TestCase):
    """The provider must receive an LLMRequest dataclass, never a dict."""

    def test_provider_receives_llm_request_instance(self):
        from services import generation_service as gs

        provider = _CannedProvider()
        with mock.patch(
            "apps.question_generation.infrastructure.providers.openai_provider.OpenAIProvider",
            return_value=provider,
        ):
            events = _collect_sse(
                gs.stream_general_instructions_questions(
                    user=None,
                    pdf_source_ids=[],
                    topic="Algebra",
                    count=2,
                    difficulty="medium",
                    instructions=(
                        "Section A: 1 short answer of 2 marks each;\n"
                        "Section B: 1 short answer of 2 marks each."
                    ),
                    payload={"subject": "Mathematics", "class": "10"},
                )
            )

        self.assertTrue(provider.requests, "provider.stream_chat was never invoked — GIM bailed early")

        # Provider only sees objects whose attribute access works — if the
        # code ever passes a dict again, the stub raises AttributeError
        # and this assert never runs.
        for req in provider.requests:
            self.assertIsInstance(req["model"], str)
            self.assertEqual(req["system_role"], "system")
            self.assertEqual(req["user_role"], "user")
            self.assertTrue(req["stream"])
            self.assertEqual(req["response_format"], {"type": "json_object"})

        # And at least one `question` event reaches the wire.
        question_events = [p for name, p in events if name == "question"]
        self.assertGreaterEqual(len(question_events), 1, "no question SSE events emitted")

    def test_two_section_instruction_produces_per_section_questions(self):
        from services import generation_service as gs

        provider = _CannedProvider()
        with mock.patch(
            "apps.question_generation.infrastructure.providers.openai_provider.OpenAIProvider",
            return_value=provider,
        ):
            events = _collect_sse(
                gs.stream_general_instructions_questions(
                    user=None,
                    pdf_source_ids=[],
                    topic="Trigonometry",
                    count=4,
                    difficulty="medium",
                    instructions=(
                        "Section A: 2 short answers of 2 marks each;\n"
                        "Section B: 2 long answers of 5 marks each."
                    ),
                    payload={"subject": "Mathematics", "class": "10"},
                )
            )

        update_events = [p for name, p in events if name == "update"]
        self.assertTrue(update_events, "no update events emitted — GIM produced no questions")

        final = update_events[-1]
        sections = final.get("sections") or []
        titles = [s.get("title") for s in sections]
        self.assertIn("Section A", titles)
        self.assertIn("Section B", titles)

        total_questions = sum(len(s.get("questions") or []) for s in sections)
        self.assertEqual(total_questions, 4)

    def test_provider_request_is_dataclass(self):
        """Belt-and-braces — assert the literal LLMRequest type to catch
        the regression where someone wraps a dict in a SimpleNamespace
        that ducks `request.model` but breaks elsewhere."""
        from services import generation_service as gs

        captured = {}

        class _AssertingProvider:
            def stream_chat(self, request):
                captured["type_name"] = type(request).__name__
                captured["is_request"] = isinstance(request, LLMRequest)
                # Yield one valid JSON so the slot completes cleanly.
                yield json.dumps({
                    "question": {
                        "content": "x",
                        "type": "SHORT_ANSWER",
                        "answer": "y",
                        "marks": 2,
                    }
                })

        with mock.patch(
            "apps.question_generation.infrastructure.providers.openai_provider.OpenAIProvider",
            return_value=_AssertingProvider(),
        ):
            list(_collect_sse(
                gs.stream_general_instructions_questions(
                    user=None,
                    pdf_source_ids=[],
                    topic="t",
                    count=1,
                    difficulty="medium",
                    instructions="1 short answer of 2 marks each.",
                    payload={"subject": "Science", "class": "10"},
                )
            ))

        self.assertTrue(captured.get("is_request"), f"expected LLMRequest, got {captured.get('type_name')!r}")


if __name__ == "__main__":
    unittest.main()
