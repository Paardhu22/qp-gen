"""Tests for on-demand question images.

The image model itself is stubbed — what a model draws is not something a test
can pin. What IS pinned: that a teacher's style choice reaches the prompt, that
the exam constraints are never dropped whichever style is picked, that the
cache key covers everything that changes the pixels, and that a failure says
something a teacher can act on.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from services.question_image import (
    STYLE_CARTOON,
    STYLE_CHOICES,
    STYLE_LINE_ART,
    STYLE_REALISTIC,
    QuestionImageError,
    build_prompt,
    generate_question_image,
    normalize_style,
)


class StyleTests(TestCase):
    def test_the_three_offered_styles_are_all_real(self):
        # The picker is served from STYLE_CHOICES; an option it offers that
        # normalize_style does not know would silently fall back to line art.
        for choice in STYLE_CHOICES:
            self.assertEqual(normalize_style(choice["value"]), choice["value"])

    def test_the_spec_styles_are_all_present(self):
        values = {c["value"] for c in STYLE_CHOICES}
        self.assertEqual(values, {STYLE_LINE_ART, STYLE_REALISTIC, STYLE_CARTOON})

    def test_an_unknown_style_falls_back_to_line_art(self):
        # Line art is the only style that is always safe on an exam paper.
        for junk in ("", None, "watercolour", "3d-render", 42):
            self.assertEqual(normalize_style(junk), STYLE_LINE_ART)

    def test_client_casing_and_separators_are_tolerated(self):
        for variant in ("Line Art", "line-art", "LINE_ART", " line art "):
            self.assertEqual(normalize_style(variant), STYLE_LINE_ART)


class PromptTests(TestCase):
    QUESTION = "Draw a labelled diagram of the human eye and mark the retina."

    def test_each_style_produces_a_visibly_different_instruction(self):
        prompts = {
            style: build_prompt(self.QUESTION, style)
            for style in (STYLE_LINE_ART, STYLE_REALISTIC, STYLE_CARTOON)
        }
        self.assertEqual(len(set(prompts.values())), 3)
        self.assertIn("line drawing", prompts[STYLE_LINE_ART])
        self.assertIn("photographic", prompts[STYLE_REALISTIC])
        self.assertIn("cartoon", prompts[STYLE_CARTOON])

    def test_exam_constraints_survive_every_style(self):
        # A teacher picking "cartoon" has not asked for a captioned meme.
        for style in (STYLE_LINE_ART, STYLE_REALISTIC, STYLE_CARTOON):
            prompt = build_prompt(self.QUESTION, style)
            self.assertIn("no title", prompt)
            self.assertIn("no caption", prompt)
            self.assertIn("no watermark", prompt)
            self.assertIn("examination paper", prompt)

    def test_the_question_is_framed_as_subject_matter_not_an_instruction(self):
        # Otherwise "Draw a labelled diagram of X" yields a picture of the
        # sentence rather than a picture of X.
        prompt = build_prompt(self.QUESTION, STYLE_LINE_ART)
        self.assertIn("do not draw the text of the question", prompt)
        self.assertIn("do not answer it", prompt)

    def test_a_long_case_study_is_trimmed(self):
        # An over-long prompt drifts, and a case study's stimulus paragraph is
        # not what the figure is of.
        prompt = build_prompt("word " * 400, STYLE_LINE_ART)
        self.assertLess(len(prompt), 2000)
        self.assertIn("…", prompt)

    def test_whitespace_is_normalised(self):
        prompt = build_prompt("a\n\n  b\t\tc", STYLE_LINE_ART)
        self.assertIn("a b c", prompt)


def _ok_response(payload=b"PNG-BYTES"):
    import base64

    item = MagicMock()
    item.b64_json = base64.b64encode(payload).decode()
    response = MagicMock()
    response.data = [item]
    return response


class GenerateTests(TestCase):
    QUESTION = "Label the parts of a plant cell."

    def _client(self, response=None, side_effect=None):
        client = MagicMock()
        if side_effect is not None:
            client.images.generate.side_effect = side_effect
        else:
            client.images.generate.return_value = response or _ok_response()
        return client

    def test_an_empty_question_is_refused_before_any_spend(self):
        with patch("services.question_image.get_openai_client") as factory:
            with self.assertRaises(QuestionImageError):
                generate_question_image(question_text="   ")
            factory.assert_not_called()

    def test_a_drawn_image_is_stored_and_returned_as_a_stable_url(self):
        client = self._client()
        with patch("services.question_image.get_openai_client", return_value=client), \
             patch("services.question_image.default_storage") as storage:
            storage.exists.return_value = False
            storage.save.side_effect = lambda path, _content: path

            result = generate_question_image(
                question_text=self.QUESTION, style=STYLE_CARTOON
            )

        self.assertFalse(result["cached"])
        self.assertEqual(result["style"], STYLE_CARTOON)
        # Never a presigned URL: it would be long expired by the time the
        # teacher reopens the paper.
        self.assertTrue(result["imageUrl"].startswith("/media/"))
        self.assertIn("question_images/", result["imageUrl"])

    def test_an_identical_request_is_served_from_cache_without_spending(self):
        with patch("services.question_image.get_openai_client") as factory, \
             patch("services.question_image.default_storage") as storage:
            storage.exists.return_value = True

            result = generate_question_image(question_text=self.QUESTION)

        self.assertTrue(result["cached"])
        factory.assert_not_called()

    def test_the_style_is_part_of_the_cache_key(self):
        # Otherwise asking for the cartoon version of a question already drawn
        # as line art would silently return the line art.
        from services.question_image import _storage_path

        paths = {
            style: _storage_path(build_prompt(self.QUESTION, style))
            for style in (STYLE_LINE_ART, STYLE_REALISTIC, STYLE_CARTOON)
        }
        self.assertEqual(len(set(paths.values())), 3)

    @override_settings(OPENAI_IMAGE_QUALITY="low")
    def test_quality_is_part_of_the_cache_key(self):
        # A stored PNG must not outlive the settings that drew it — raising
        # the quality tier has to actually redraw.
        from services.question_image import _storage_path

        low = _storage_path(build_prompt(self.QUESTION, STYLE_LINE_ART))
        with override_settings(OPENAI_IMAGE_QUALITY="high"):
            high = _storage_path(build_prompt(self.QUESTION, STYLE_LINE_ART))
        self.assertNotEqual(low, high)

    def test_a_model_failure_raises_something_a_teacher_can_act_on(self):
        client = self._client(side_effect=RuntimeError("rate limited"))
        with patch("services.question_image.get_openai_client", return_value=client), \
             patch("services.question_image.default_storage") as storage:
            storage.exists.return_value = False
            with self.assertRaises(QuestionImageError) as caught:
                generate_question_image(question_text=self.QUESTION)

        message = str(caught.exception)
        self.assertIn("try again", message.lower())
        # The raw exception is for the log, not for the teacher.
        self.assertNotIn("rate limited", message)

    def test_an_empty_response_is_an_error_not_a_blank_image(self):
        empty = MagicMock()
        empty.data = []
        client = self._client(response=empty)
        with patch("services.question_image.get_openai_client", return_value=client), \
             patch("services.question_image.default_storage") as storage:
            storage.exists.return_value = False
            with self.assertRaises(QuestionImageError):
                generate_question_image(question_text=self.QUESTION)

    @override_settings(OPENAI_IMAGE_MODEL="dall-e-3")
    def test_quality_is_omitted_for_models_that_do_not_accept_it(self):
        # gpt-image-1 takes low|medium|high; dall-e uses standard|hd, so
        # passing ours is a BadRequestError.
        client = self._client()
        with patch("services.question_image.get_openai_client", return_value=client), \
             patch("services.question_image.default_storage") as storage:
            storage.exists.return_value = False
            storage.save.side_effect = lambda path, _content: path
            generate_question_image(question_text=self.QUESTION)

        kwargs = client.images.generate.call_args.kwargs
        self.assertNotIn("quality", kwargs)

    def test_quality_is_sent_for_gpt_image(self):
        client = self._client()
        with patch("services.question_image.get_openai_client", return_value=client), \
             patch("services.question_image.default_storage") as storage:
            storage.exists.return_value = False
            storage.save.side_effect = lambda path, _content: path
            generate_question_image(question_text=self.QUESTION)

        self.assertIn("quality", client.images.generate.call_args.kwargs)
