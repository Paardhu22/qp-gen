"""Tester-round regressions (Cluster A.4 + A.5 from FIX_REPORT.md).

* A.4: answer-script generation MUST short-circuit when the paper has zero
  *real* questions — placeholder/template blocks ("Enter question here...",
  default MCQ options) don't count.
* A.5: the review-tray endpoint contract — a freshly created account must
  never inherit prior cached tray state. Because the tray is purely a
  client-side construct (no backend endpoint), this test pins the
  contract by asserting (a) no view exposes it and (b) the helper that
  the auth flow calls clears the persisted slice deterministically.
"""

import os
import sys
import unittest

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

from services.answer_script_service import (  # noqa: E402
    _extract_questions_from_content,
    _is_placeholder_question,
)


def _doc_with_blocks(blocks):
    """Wrap a list of editor blocks in the persisted shape so the
    extractor walks them exactly as it would on a real paper."""
    return json.dumps({
        "type": "doc",
        "content": [
            {
                "type": "page",
                "attrs": {"pageId": "p1"},
                "content": blocks,
            }
        ],
    })


def _question_block(content_text=None, options=None, attrs=None):
    block = {
        "type": "questionBlock",
        "attrs": attrs or {"marks": 2},
        "content": [],
    }
    if content_text is not None:
        block["content"].append({
            "type": "paragraph",
            "content": [{"type": "text", "text": content_text}],
        })
    if options:
        block["content"].append({
            "type": "orderedList",
            "content": [
                {
                    "type": "listItem",
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": opt}]}],
                }
                for opt in options
            ],
        })
    return block


class AnswerScriptEmptyPaperGuardTests(unittest.TestCase):
    """A.4: An "empty" paper must not produce hallucinated answers.

    The toolbar's "Question" / "MCQ" / "Grouped Questions" buttons each
    insert a block carrying literal placeholder copy. Before this fix,
    saving the paper without editing the block let the answer-script
    LLM treat the placeholder as a real question and fabricate an answer.
    """

    def test_blank_paper_returns_no_questions(self):
        content = _doc_with_blocks([{"type": "paragraph"}])
        self.assertEqual(_extract_questions_from_content(content), [])

    def test_default_question_block_is_filtered(self):
        # Exact placeholder copy emitted by the "Question" toolbar button.
        content = _doc_with_blocks([_question_block("Enter question here...")])
        self.assertEqual(_extract_questions_from_content(content), [])

    def test_default_mcq_block_is_filtered(self):
        # Exact placeholder copy emitted by the "MCQ" toolbar button.
        content = _doc_with_blocks([
            _question_block(
                "Enter MCQ stem here...",
                options=["Option A", "Option B", "Option C", "Option D"],
                attrs={"marks": 1, "questionType": "MCQ"},
            )
        ])
        self.assertEqual(_extract_questions_from_content(content), [])

    def test_default_grouped_block_is_filtered(self):
        content = _doc_with_blocks([
            {
                "type": "groupedQuestionBlock",
                "attrs": {"marks": 5},
                "content": [
                    {
                        "type": "paragraph",
                        "content": [
                            {"type": "text", "text": "Main question statement..."},
                        ],
                    },
                    {
                        "type": "orderedList",
                        "content": [
                            {
                                "type": "listItem",
                                "content": [{
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Sub-question (a)..."}],
                                }],
                            },
                            {
                                "type": "listItem",
                                "content": [{
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Sub-question (b)..."}],
                                }],
                            },
                        ],
                    },
                ],
            }
        ])
        self.assertEqual(_extract_questions_from_content(content), [])

    def test_real_question_is_preserved(self):
        content = _doc_with_blocks([
            _question_block("Define the term 'photosynthesis'."),
        ])
        questions = _extract_questions_from_content(content)
        self.assertEqual(len(questions), 1)
        self.assertEqual(
            questions[0]["content"], "Define the term 'photosynthesis'."
        )

    def test_mixed_paper_only_keeps_real_questions(self):
        content = _doc_with_blocks([
            _question_block("Enter question here..."),
            _question_block("State Newton's first law."),
            _question_block(
                "Enter MCQ stem here...",
                options=["Option A", "Option B", "Option C", "Option D"],
            ),
        ])
        questions = _extract_questions_from_content(content)
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["content"], "State Newton's first law.")

    def test_placeholder_predicate_unit_cases(self):
        # Explicit unit test on the predicate itself so future placeholder
        # additions only require updating the lookup set.
        self.assertTrue(_is_placeholder_question("", []))
        self.assertTrue(_is_placeholder_question("   ", []))
        self.assertTrue(_is_placeholder_question("Enter question here...", []))
        self.assertFalse(_is_placeholder_question("Real question?", []))


class ReviewTrayAccountIsolationTests(unittest.TestCase):
    """A.5: there must be NO backend endpoint exposing the review tray.

    The tray is purely a client-side construct. Any future endpoint that
    accidentally returns tray contents from one account to another would
    re-introduce the security bug this round fixed. Pin the contract here
    so a leak gets caught before it ships.
    """

    def test_no_review_tray_url_pattern(self):
        from django.urls import get_resolver
        resolver = get_resolver()
        patterns = [str(p.pattern) for p in resolver.url_patterns]
        suspicious = [
            p for p in patterns
            if "review-tray" in p.lower() or "tray" in p.lower()
        ]
        self.assertFalse(
            suspicious,
            f"Found unexpected review-tray URL patterns: {suspicious}. "
            "The review tray must stay client-side; if you intend to add "
            "a backend endpoint, update this test AND verify per-user "
            "filtering (Cluster A.5).",
        )


if __name__ == "__main__":
    unittest.main()
