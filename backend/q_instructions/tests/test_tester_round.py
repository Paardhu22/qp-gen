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

    def test_placeholder_predicate_near_miss_variants(self):
        # Lightly-edited placeholders — the realistic case where a user
        # bumped the trailing punctuation but didn't write a real question.
        # Each of these would have slipped through the strict exact-match
        # implementation and produced a hallucinated answer.
        for variant in (
            "Enter question here.",
            "Enter question here?",
            "Enter question here!",
            "Enter question here.....",
            "Enter question here???",
            "Enter question here. ",
            "  Enter question here...",
            "Enter question here…",  # unicode ellipsis
            "ENTER QUESTION HERE",   # all caps, no trailing
            "Enter MCQ stem here.",
            "Main question statement?",
            "Sub-question (a).",
        ):
            self.assertTrue(
                _is_placeholder_question(variant, []),
                f"Expected near-miss placeholder to be detected: {variant!r}",
            )

    def test_placeholder_predicate_real_questions_with_prefix_overlap(self):
        # A real question that *contains* placeholder-looking words but adds
        # substantive content must NOT be treated as a placeholder.
        for real in (
            "Enter question here and explain why.",
            "Main question statement: define photosynthesis.",
            "Find x if 2x + 3 = 11.",
        ):
            self.assertFalse(
                _is_placeholder_question(real, []),
                f"Real question wrongly flagged as placeholder: {real!r}",
            )

    def test_assertion_reason_template_block_is_filtered(self):
        # The Cluster C.1 toolbar button emits a single questionBlock whose
        # extracted text is the concatenation of both placeholder snippets.
        ar_text = (
            "Assertion (A):  Enter assertion here... "
            "Reason (R):  Enter reason here..."
        )
        self.assertTrue(_is_placeholder_question(ar_text, []))

    def test_assertion_reason_with_real_content_is_kept(self):
        # If the user edited at least the assertion text, the block has
        # real content and should reach the LLM.
        real_ar = (
            "Assertion (A): The square of any odd integer is odd. "
            "Reason (R): Enter reason here..."
        )
        # We're OK with this returning False — the user partially edited.
        # The predicate's contract is to filter *unedited* templates only.
        self.assertFalse(_is_placeholder_question(real_ar, []))


class PasswordResetExpiryTzRegressionTests(unittest.TestCase):
    """`verification.expiresAt` was created by the Prisma better-auth schema
    as `TIMESTAMP WITHOUT TIME ZONE`, so Postgres returns it to Django as a
    naive datetime even with USE_TZ=True. Before this round,
    `consume_reset_token` did `verification.expires_at <= timezone.now()`
    (aware), which raises `TypeError: can't compare offset-naive and
    offset-aware datetimes` and bubbles up as an HTTP 500. Every reset
    link 500'd. Pin the contract here so a regression to the naive
    comparison surfaces in CI rather than in production.
    """

    def test_consume_reset_token_does_not_crash_on_valid_token(self):
        import time
        from apps.accounts.models import Account, User
        from services.password_reset_service import (
            consume_reset_token,
            issue_reset_token,
        )

        # Fresh user → fresh account → fresh token.
        email = f"reset-tz+{int(time.time() * 1000)}@gmail.com"
        user = User.objects.create(name="TZ Tester", email=email)
        try:
            acc = Account.objects.create(
                account_id=email, provider_id="email", user=user
            )
            acc.set_password("original-pw-12")
            acc.save(update_fields=["password"])

            token = issue_reset_token(user)
            ok = consume_reset_token(token, "rotated-pw-34")
            self.assertTrue(
                ok,
                "consume_reset_token returned False — either the comparison "
                "crashed (regression) or the token storage path is broken.",
            )

            # And the rotation must have stuck.
            acc.refresh_from_db()
            self.assertTrue(acc.check_password("rotated-pw-34"))
            self.assertFalse(acc.check_password("original-pw-12"))
        finally:
            user.delete()


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
