"""Tests for the General Instructions design endpoint and paper templates.

The design call itself is stubbed — what a model returns is not a thing a test
can pin down. What IS pinned down: that stated settings are never re-asked,
that only the three genuinely un-inferable constraints block, and that a
template belongs to exactly one teacher.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.generation.models import PaperTemplate
from services.paper_design import DesignSection, PaperDesign, QuestionGroup


def a_design(*, marks=2, count=10, title="Section A"):
    return PaperDesign(
        sections=[
            DesignSection(
                title,
                [QuestionGroup(question_type="SHORT_ANSWER", marks=marks, count=count)],
            )
        ]
    )


class DesignApiTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create(email="t@example.com", name="T")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)


class DesignPaperViewTests(DesignApiTestCase):
    URL = "/api/generation/design-paper"

    def test_blank_instructions_are_rejected_before_any_model_call(self):
        with patch("apps.generation.design_views.design_paper") as designer:
            response = self.client.post(self.URL, {"instructions": "   "}, format="json")
        self.assertEqual(response.status_code, 400)
        designer.assert_not_called()

    def test_absurdly_long_instructions_are_rejected(self):
        with patch("apps.generation.design_views.design_paper") as designer:
            response = self.client.post(
                self.URL, {"instructions": "x" * 9000}, format="json"
            )
        self.assertEqual(response.status_code, 400)
        designer.assert_not_called()

    def test_a_design_comes_back_with_its_totals(self):
        with patch(
            "apps.generation.design_views.design_paper", return_value=a_design()
        ):
            response = self.client.post(
                self.URL,
                {
                    "instructions": "10 short answers of 2 marks",
                    "settings": {"subject": "Science", "academicClass": "10"},
                    "pdfSourceIds": ["doc1"],
                },
                format="json",
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["design"]["totalQuestions"], 10)
        self.assertEqual(body["design"]["totalMarks"], 20)
        self.assertTrue(body["ready"])

    def test_a_forgotten_difficulty_is_assumed_and_does_not_block(self):
        with patch(
            "apps.generation.design_views.design_paper", return_value=a_design()
        ):
            response = self.client.post(
                self.URL,
                {
                    "instructions": "10 short answers",
                    "settings": {"subject": "Science", "academicClass": "10"},
                    "hsatSourceIds": ["src1"],
                },
                format="json",
            )
        body = response.json()
        self.assertTrue(body["ready"], "an assumption must not block generation")
        difficulty = next(g for g in body["gaps"] if g["field"] == "difficulty")
        self.assertEqual(difficulty["kind"], "assumed")
        self.assertEqual(body["settings"]["difficulty"], "medium")

    def test_missing_subject_class_and_sources_block(self):
        with patch(
            "apps.generation.design_views.design_paper", return_value=a_design()
        ):
            response = self.client.post(
                self.URL, {"instructions": "10 short answers"}, format="json"
            )
        body = response.json()
        self.assertFalse(body["ready"])
        blocking = {g["field"] for g in body["gaps"] if g["kind"] == "required"}
        self.assertEqual(blocking, {"subject", "academicClass", "sources"})

    def test_settings_stated_in_prose_are_not_re_asked(self):
        # The whole point: a teacher who wrote "class 10 science, hard" must
        # not then be asked for class, subject or difficulty.
        with patch(
            "apps.generation.design_views.design_paper", return_value=a_design()
        ):
            response = self.client.post(
                self.URL,
                {
                    "instructions": "class 10 science weekly test, hard, 20 marks",
                    "pdfSourceIds": ["doc1"],
                },
                format="json",
            )
        body = response.json()
        self.assertTrue(body["ready"])
        self.assertEqual(body["settings"]["subject"], "Science")
        self.assertEqual(body["settings"]["academicClass"], "10")
        self.assertEqual(body["settings"]["difficulty"], "hard")

    def test_explicit_settings_beat_what_the_prose_implies(self):
        # The form is the teacher's latest word; prose is a first guess.
        with patch(
            "apps.generation.design_views.design_paper", return_value=a_design()
        ):
            response = self.client.post(
                self.URL,
                {
                    "instructions": "class 10 science test, easy",
                    "settings": {"difficulty": "hard", "academicClass": "9"},
                    "pdfSourceIds": ["doc1"],
                },
                format="json",
            )
        settings_out = response.json()["settings"]
        self.assertEqual(settings_out["difficulty"], "hard")
        self.assertEqual(settings_out["academicClass"], "9")

    def test_the_stated_total_reaches_the_designer(self):
        with patch(
            "apps.generation.design_views.design_paper", return_value=a_design()
        ) as designer:
            self.client.post(
                self.URL,
                {
                    "instructions": "a test",
                    "settings": {"marks": "40", "subject": "Science"},
                    "pdfSourceIds": ["doc1"],
                },
                format="json",
            )
        self.assertEqual(designer.call_args.kwargs["total_marks"], 40)

    def test_a_blank_marks_field_is_not_sent_as_zero(self):
        with patch(
            "apps.generation.design_views.design_paper", return_value=a_design()
        ) as designer:
            self.client.post(
                self.URL,
                {"instructions": "a test", "settings": {"marks": ""}},
                format="json",
            )
        self.assertIsNone(designer.call_args.kwargs["total_marks"])

    def test_general_instructions_are_returned_for_the_paper_header(self):
        with patch(
            "apps.generation.design_views.design_paper", return_value=a_design(count=6)
        ):
            response = self.client.post(
                self.URL,
                {"instructions": "6 short answers", "pdfSourceIds": ["d"]},
                format="json",
            )
        lines = response.json()["generalInstructions"]
        self.assertTrue(any("6 questions" in line for line in lines))

    def test_the_endpoint_requires_authentication(self):
        response = APIClient().post(self.URL, {"instructions": "x"}, format="json")
        self.assertIn(response.status_code, (401, 403))


class PaperTemplateTests(DesignApiTestCase):
    URL = "/api/generation/templates"

    def test_a_template_round_trips(self):
        response = self.client.post(
            self.URL,
            {
                "name": "Weekly Test",
                "instructions": "3 MCQ, 4 short answers of 2 marks, 1 long of 5",
                "settings": {"difficulty": "medium", "marks": "20", "subject": "Science"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        listed = self.client.get(self.URL).json()["templates"]
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["name"], "Weekly Test")
        # Both halves survive: the prose the designer reads, and the answers
        # that stop it re-asking.
        self.assertIn("3 MCQ", listed[0]["instructions"])
        self.assertEqual(listed[0]["settings"]["difficulty"], "medium")

    def test_a_template_needs_a_name_and_instructions(self):
        for payload in (
            {"name": "", "instructions": "3 MCQ"},
            {"name": "Weekly", "instructions": "  "},
        ):
            response = self.client.post(self.URL, payload, format="json")
            self.assertEqual(response.status_code, 400, payload)
        self.assertEqual(PaperTemplate.objects.count(), 0)

    def test_saving_the_same_name_twice_overwrites_rather_than_duplicating(self):
        self.client.post(
            self.URL, {"name": "Weekly Test", "instructions": "v1"}, format="json"
        )
        response = self.client.post(
            self.URL,
            {"name": "Weekly Test", "instructions": "v2", "settings": {"marks": "30"}},
            format="json",
        )
        self.assertEqual(response.status_code, 200, "an update, not a create")
        self.assertEqual(PaperTemplate.objects.filter(user=self.user).count(), 1)
        template = PaperTemplate.objects.get(user=self.user)
        self.assertEqual(template.instructions, "v2")
        self.assertEqual(template.settings["marks"], "30")

    def test_two_teachers_may_each_have_a_weekly_test(self):
        other = User.objects.create(email="o@example.com", name="O")
        PaperTemplate.objects.create(
            user=other, name="Weekly Test", instructions="theirs"
        )
        response = self.client.post(
            self.URL, {"name": "Weekly Test", "instructions": "mine"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(PaperTemplate.objects.count(), 2)

    def test_a_teacher_only_sees_their_own_templates(self):
        other = User.objects.create(email="o@example.com", name="O")
        PaperTemplate.objects.create(user=other, name="Theirs", instructions="x")
        PaperTemplate.objects.create(user=self.user, name="Mine", instructions="y")

        listed = self.client.get(self.URL).json()["templates"]
        self.assertEqual([t["name"] for t in listed], ["Mine"])

    def test_applying_a_template_marks_it_used(self):
        template = PaperTemplate.objects.create(
            user=self.user, name="Weekly", instructions="3 MCQ"
        )
        self.assertIsNone(template.last_used_at)

        response = self.client.post(f"{self.URL}/{template.id}", format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["template"]["instructions"], "3 MCQ")

        template.refresh_from_db()
        self.assertIsNotNone(template.last_used_at)

    def test_recently_used_templates_sort_first(self):
        from django.utils import timezone

        PaperTemplate.objects.create(user=self.user, name="Old", instructions="a")
        recent = PaperTemplate.objects.create(
            user=self.user, name="Recent", instructions="b"
        )
        recent.last_used_at = timezone.now()
        recent.save(update_fields=["last_used_at"])

        listed = self.client.get(self.URL).json()["templates"]
        self.assertEqual(listed[0]["name"], "Recent")

    def test_another_teachers_template_is_not_reachable(self):
        other = User.objects.create(email="o@example.com", name="O")
        theirs = PaperTemplate.objects.create(
            user=other, name="Theirs", instructions="secret"
        )
        self.assertEqual(self.client.post(f"{self.URL}/{theirs.id}").status_code, 404)
        self.assertEqual(self.client.delete(f"{self.URL}/{theirs.id}").status_code, 404)
        self.assertTrue(PaperTemplate.objects.filter(id=theirs.id).exists())

    def test_a_template_can_be_deleted(self):
        template = PaperTemplate.objects.create(
            user=self.user, name="Weekly", instructions="x"
        )
        self.assertEqual(self.client.delete(f"{self.URL}/{template.id}").status_code, 204)
        self.assertFalse(PaperTemplate.objects.filter(id=template.id).exists())

    def test_templates_require_authentication(self):
        anonymous = APIClient()
        self.assertIn(anonymous.get(self.URL).status_code, (401, 403))
        self.assertIn(
            anonymous.post(self.URL, {"name": "x", "instructions": "y"}).status_code,
            (401, 403),
        )
