"""Manual drawing instructions must survive the API boundary without live model calls."""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.generation.design_views import QuestionImageView


class QuestionImageApiTests(SimpleTestCase):
    def post(self, **fields):
        request = APIRequestFactory().post(
            "/api/generation/question-image",
            {"questionText": "Find the tangent length.", "style": "line_art", **fields},
            format="json",
        )
        force_authenticate(request, user=SimpleNamespace(is_authenticated=True, status="approved", is_superadmin=False))
        return QuestionImageView.as_view()(request)

    @patch("apps.generation.design_views.check_monthly_token_limit")
    @patch("services.generation.question_image.generate_question_image")
    def test_description_is_forwarded_with_question_and_style(self, generate, _limit):
        generate.return_value = {"imageUrl": "/media/figure.png", "style": "cartoon", "cached": False}
        response = self.post(style="cartoon", imageDescription="  A circle with two tangents.  ")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(generate.call_args.kwargs["image_description"], "A circle with two tangents.")
        self.assertEqual(generate.call_args.kwargs["question_text"], "Find the tangent length.")
        self.assertEqual(generate.call_args.kwargs["style"], "cartoon")

    @patch("apps.generation.design_views.check_monthly_token_limit")
    @patch("services.generation.question_image.generate_question_image")
    def test_existing_automatic_requests_still_work(self, generate, _limit):
        generate.return_value = {"imageUrl": "/media/figure.png", "style": "line_art", "cached": True}
        self.assertEqual(self.post().status_code, 200)
        self.assertEqual(generate.call_args.kwargs["image_description"], "")

    @patch("apps.generation.design_views.check_monthly_token_limit")
    @patch("services.generation.question_image.generate_question_image")
    def test_invalid_descriptions_are_rejected_before_spend(self, generate, limit):
        for value in ("x" * 2001, ["a diagram"], {"text": "a diagram"}, 42, None):
            with self.subTest(value=type(value).__name__):
                self.assertEqual(self.post(imageDescription=value).status_code, 400)
        limit.assert_not_called()
        generate.assert_not_called()
