"""Tests for the General Instructions design endpoint and paper templates.

The design call itself is stubbed — what a model returns is not a thing a test
can pin down. What IS pinned down: that stated settings are never re-asked,
that only the three genuinely un-inferable constraints block, and that a
template belongs to exactly one teacher.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.generation.models import PaperTemplate, TemplateFolder
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
        self.user = User.objects.create(email="t@example.com", name="T", status="approved")
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

    def test_a_template_needs_a_name(self):
        for payload in (
            {"name": "", "instructions": "3 MCQ"},
            {"name": "   ", "instructions": "3 MCQ"},
        ):
            response = self.client.post(self.URL, payload, format="json")
            self.assertEqual(response.status_code, 400, payload)
        self.assertEqual(PaperTemplate.objects.count(), 0)

    def test_a_template_with_blank_instructions_is_allowed(self):
        # Blank templates can be created from the Templates UI so they can be
        # filed into a folder and filled in later — see design_views.py.
        response = self.client.post(
            self.URL, {"name": "Weekly", "instructions": "  "}, format="json"
        )
        self.assertEqual(response.status_code, 201)

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
        other = User.objects.create(email="o@example.com", name="O", status="approved")
        PaperTemplate.objects.create(
            user=other, name="Weekly Test", instructions="theirs"
        )
        response = self.client.post(
            self.URL, {"name": "Weekly Test", "instructions": "mine"}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(PaperTemplate.objects.count(), 2)

    def test_a_teacher_only_sees_their_own_templates(self):
        other = User.objects.create(email="o@example.com", name="O", status="approved")
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
        other = User.objects.create(email="o@example.com", name="O", status="approved")
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


class TemplateCatalogApiTests(DesignApiTestCase):
    """The picker endpoint: built-ins and saved templates in one response."""

    LIST_URL = "/api/generation/templates"
    RESOLVE_URL = "/api/generation/templates/resolve"
    TYPES_URL = "/api/generation/question-types"

    def test_the_list_returns_builtins_alongside_saved_templates(self):
        PaperTemplate.objects.create(
            user=self.user, name="Weekly Test", instructions="20 mark recap"
        )
        response = self.client.get(self.LIST_URL)
        self.assertEqual(response.status_code, 200)

        self.assertEqual(len(response.data["templates"]), 1)
        self.assertEqual(response.data["templates"][0]["name"], "Weekly Test")
        # Both old modes have to be reachable from the one picker.
        builtin_ids = {entry["id"] for entry in response.data["builtin"]}
        self.assertIn("describe-it-yourself", builtin_ids)
        self.assertIn("cbse-science-10", builtin_ids)

    def test_resolve_needs_a_template_id(self):
        response = self.client.post(self.RESOLVE_URL, {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_an_unknown_template_is_a_404_not_a_500(self):
        response = self.client.post(
            self.RESOLVE_URL, {"templateId": "nope"}, format="json"
        )
        self.assertEqual(response.status_code, 404)

    def test_resolving_blank_returns_an_empty_editable_blueprint(self):
        response = self.client.post(
            self.RESOLVE_URL, {"templateId": "blank"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["blueprint"]["slots"], [])
        self.assertEqual(response.data["blueprint"]["totalMarks"], 0)

    def test_resolving_a_board_template_produces_slots_with_totals(self):
        response = self.client.post(
            self.RESOLVE_URL,
            {"templateId": "cbse-science-10", "subject": "Science", "class": "10"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        blueprint = response.data["blueprint"]
        self.assertGreater(len(blueprint["slots"]), 0)
        # Totals must agree with the slots they describe.
        self.assertEqual(blueprint["totalQuestions"], len(blueprint["slots"]))
        self.assertEqual(
            blueprint["totalMarks"], sum(s["marks"] for s in blueprint["slots"])
        )
        # Every slot must carry a type the Builder can render in its menu.
        for slot in blueprint["slots"]:
            self.assertTrue(slot["questionType"])
            self.assertIn(slot["source"], ("generate", "saved"))

    def test_the_saved_ratio_can_be_applied_at_resolve_time(self):
        response = self.client.post(
            self.RESOLVE_URL,
            {"templateId": "cbse-science-10", "savedCount": 5},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["blueprint"]["savedCount"], 5)

    def test_a_pinned_template_resolves_from_its_stored_blueprint(self):
        # The whole point of pinning: an edited slot survives, rather than
        # being re-derived from prose that never mentioned it.
        PaperTemplate.objects.create(
            user=self.user,
            name="Pinned",
            instructions="anything",
            blueprint={
                "slots": [
                    {"questionType": "MCQ", "marks": 1, "sectionTitle": "A"},
                    {"questionType": "LONG_ANSWER", "marks": 5, "sectionTitle": "B"},
                ]
            },
        )
        template = PaperTemplate.objects.get(user=self.user, name="Pinned")
        response = self.client.post(
            self.RESOLVE_URL, {"templateId": template.id}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        slots = response.data["blueprint"]["slots"]
        self.assertEqual([s["questionType"] for s in slots], ["MCQ", "LONG_ANSWER"])
        self.assertEqual(response.data["blueprint"]["totalMarks"], 6)

    def test_another_teachers_template_id_is_not_resolvable(self):
        other = User.objects.create(email="other@example.com", name="O", status="approved")
        theirs = PaperTemplate.objects.create(
            user=other, name="Theirs", blueprint={"slots": [{"questionType": "MCQ"}]}
        )
        response = self.client.post(
            self.RESOLVE_URL, {"templateId": theirs.id}, format="json"
        )
        # Falls through to the built-in path and finds nothing — never another
        # teacher's paper recipe.
        self.assertEqual(response.status_code, 404)

    def test_a_blueprint_only_template_can_be_saved_without_instructions(self):
        # A teacher who dragged slots around should not also have to write
        # prose describing what they just did.
        response = self.client.post(
            self.LIST_URL,
            {
                "name": "My Midterm",
                "blueprint": {"slots": [{"questionType": "MCQ", "marks": 1}]},
                "baseTemplateId": "cbse-science-10",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["template"]["pinned"])
        self.assertEqual(
            response.data["template"]["base_template_id"], "cbse-science-10"
        )

    def test_a_template_with_neither_instructions_nor_blueprint_is_allowed(self):
        # A blank template is a normal resting state — see design_views.py.
        response = self.client.post(
            self.LIST_URL, {"name": "Empty"}, format="json"
        )
        self.assertEqual(response.status_code, 201)

    def test_the_question_type_menu_is_served(self):
        response = self.client.get(self.TYPES_URL, {"subject": "Science"})
        self.assertEqual(response.status_code, 200)
        codes = {option["code"] for option in response.data["questionTypes"]}
        self.assertIn("MCQ", codes)
        self.assertIn("LONG_ANSWER", codes)


class TemplateFolderTests(DesignApiTestCase):
    """Filing is the teacher's own structure, and it must never cost them work.

    The properties that matter are about what a folder operation CANNOT do:
    delete a paper recipe, produce a tree that will not render, or expose
    another account's filing.
    """

    URL = "/api/generation/template-folders"

    def test_a_folder_round_trips_with_its_template_count(self):
        created = self.client.post(self.URL, {"name": "Term 1"}, format="json")
        self.assertEqual(created.status_code, 201)
        folder_id = created.json()["folder"]["id"]

        PaperTemplate.objects.create(
            user=self.user,
            name="Weekly",
            instructions="3 MCQ",
            folder_id=folder_id,
        )

        listed = self.client.get(self.URL).json()["folders"]
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["name"], "Term 1")
        self.assertEqual(listed[0]["templateCount"], 1)
        self.assertIsNone(listed[0]["parentId"])

    def test_a_folder_needs_a_name(self):
        response = self.client.post(self.URL, {"name": "   "}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(TemplateFolder.objects.count(), 0)

    def test_two_root_folders_cannot_share_a_name(self):
        """The nullable-parent trap: SQL treats NULLs as distinct, so a single
        (user, parent, name) constraint would wave this through."""
        self.client.post(self.URL, {"name": "Term 1"}, format="json")
        response = self.client.post(self.URL, {"name": "Term 1"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(TemplateFolder.objects.count(), 1)

    def test_the_same_name_may_appear_under_different_parents(self):
        a = self.client.post(self.URL, {"name": "Term 1"}, format="json").json()
        b = self.client.post(self.URL, {"name": "Term 2"}, format="json").json()

        for parent in (a["folder"]["id"], b["folder"]["id"]):
            response = self.client.post(
                self.URL, {"name": "Unit tests", "parentId": parent}, format="json"
            )
            self.assertEqual(response.status_code, 201)

    def test_deleting_a_folder_unfiles_its_templates_rather_than_deleting_them(self):
        folder = TemplateFolder.objects.create(user=self.user, name="Term 1")
        template = PaperTemplate.objects.create(
            user=self.user, name="Weekly", instructions="3 MCQ", folder=folder
        )

        response = self.client.delete(f"{self.URL}/{folder.id}")
        self.assertEqual(response.status_code, 204)

        template.refresh_from_db()
        self.assertIsNone(template.folder_id, "the template should be unfiled")

    def test_deleting_a_parent_takes_its_subfolders_but_spares_the_templates(self):
        parent = TemplateFolder.objects.create(user=self.user, name="Term 1")
        child = TemplateFolder.objects.create(
            user=self.user, name="Unit tests", parent=parent
        )
        template = PaperTemplate.objects.create(
            user=self.user, name="Weekly", instructions="3 MCQ", folder=child
        )

        self.client.delete(f"{self.URL}/{parent.id}")

        self.assertEqual(TemplateFolder.objects.count(), 0)
        template.refresh_from_db()
        self.assertIsNone(template.folder_id)

    def test_nesting_stops_at_the_depth_cap(self):
        parent_id = None
        for level in range(3):
            response = self.client.post(
                self.URL, {"name": f"L{level}", "parentId": parent_id}, format="json"
            )
            self.assertEqual(response.status_code, 201, f"level {level}")
            parent_id = response.json()["folder"]["id"]

        too_deep = self.client.post(
            self.URL, {"name": "L3", "parentId": parent_id}, format="json"
        )
        self.assertEqual(too_deep.status_code, 400)

    def test_a_folder_cannot_be_moved_inside_itself(self):
        folder = TemplateFolder.objects.create(user=self.user, name="Term 1")
        response = self.client.patch(
            f"{self.URL}/{folder.id}", {"parentId": folder.id}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_a_folder_cannot_be_moved_inside_its_own_descendant(self):
        """The cycle a self-FK is perfectly happy to store, and which would
        make the folder rail unrenderable."""
        parent = TemplateFolder.objects.create(user=self.user, name="Term 1")
        child = TemplateFolder.objects.create(
            user=self.user, name="Unit tests", parent=parent
        )

        response = self.client.patch(
            f"{self.URL}/{parent.id}", {"parentId": child.id}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        parent.refresh_from_db()
        self.assertIsNone(parent.parent_id)

    def test_moving_a_subtree_respects_the_depth_cap(self):
        deep_parent = TemplateFolder.objects.create(user=self.user, name="A")
        TemplateFolder.objects.create(user=self.user, name="B", parent=deep_parent)

        landing = TemplateFolder.objects.create(user=self.user, name="C")
        nested_landing = TemplateFolder.objects.create(
            user=self.user, name="D", parent=landing
        )

        # A carries a child, so filing it under D would put B at depth 3.
        response = self.client.patch(
            f"{self.URL}/{deep_parent.id}",
            {"parentId": nested_landing.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_a_folder_can_be_renamed(self):
        folder = TemplateFolder.objects.create(user=self.user, name="Term 1")
        response = self.client.patch(
            f"{self.URL}/{folder.id}", {"name": "Term One"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        folder.refresh_from_db()
        self.assertEqual(folder.name, "Term One")

    def test_another_teachers_folder_is_not_found(self):
        other = User.objects.create(email="o@example.com", name="O", status="approved")
        theirs = TemplateFolder.objects.create(user=other, name="Theirs")

        self.assertEqual(self.client.get(self.URL).json()["folders"], [])
        self.assertEqual(
            self.client.patch(
                f"{self.URL}/{theirs.id}", {"name": "Mine now"}, format="json"
            ).status_code,
            404,
        )
        self.assertEqual(self.client.delete(f"{self.URL}/{theirs.id}").status_code, 404)
        self.assertTrue(TemplateFolder.objects.filter(id=theirs.id).exists())


class PaperTemplateEditTests(DesignApiTestCase):
    """PATCH edits a recipe; POST only records that it was used.

    The property under test throughout is that an edit touches exactly what the
    body named — a rename must not blank a blueprint.
    """

    URL = "/api/generation/templates"

    def setUp(self):
        super().setUp()
        self.template = PaperTemplate.objects.create(
            user=self.user,
            name="Weekly",
            instructions="3 MCQ",
            blueprint={"slots": [{"questionType": "MCQ", "marks": 1, "index": 0}]},
            settings={"difficulty": "medium"},
        )

    def test_renaming_leaves_the_blueprint_alone(self):
        response = self.client.patch(
            f"{self.URL}/{self.template.id}", {"name": "Friday Recap"}, format="json"
        )
        self.assertEqual(response.status_code, 200)

        self.template.refresh_from_db()
        self.assertEqual(self.template.name, "Friday Recap")
        self.assertEqual(self.template.instructions, "3 MCQ")
        self.assertTrue(self.template.blueprint["slots"])
        self.assertEqual(self.template.settings["difficulty"], "medium")

    def test_a_template_can_be_filed_and_unfiled(self):
        folder = TemplateFolder.objects.create(user=self.user, name="Term 1")

        filed = self.client.patch(
            f"{self.URL}/{self.template.id}", {"folderId": folder.id}, format="json"
        )
        self.assertEqual(filed.status_code, 200)
        self.assertEqual(filed.json()["template"]["folderId"], folder.id)

        unfiled = self.client.patch(
            f"{self.URL}/{self.template.id}", {"folderId": None}, format="json"
        )
        self.assertEqual(unfiled.status_code, 200)
        self.assertIsNone(unfiled.json()["template"]["folderId"])

    def test_clearing_the_blueprint_reverts_to_instruction_driven(self):
        response = self.client.patch(
            f"{self.URL}/{self.template.id}", {"blueprint": None}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["template"]["pinned"])

    def test_a_template_cannot_be_edited_into_something_unreproducible(self):
        """Stripping both halves would leave a row that names a paper it
        cannot rebuild."""
        pinned_only = PaperTemplate.objects.create(
            user=self.user,
            name="Slots only",
            instructions="",
            blueprint={"slots": [{"questionType": "MCQ", "marks": 1, "index": 0}]},
        )
        response = self.client.patch(
            f"{self.URL}/{pinned_only.id}", {"blueprint": None}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        pinned_only.refresh_from_db()
        self.assertTrue(pinned_only.blueprint["slots"], "the edit must not stick")

    def test_an_empty_patch_is_rejected(self):
        response = self.client.patch(
            f"{self.URL}/{self.template.id}", {}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_filing_into_a_folder_that_is_gone_is_a_404(self):
        response = self.client.patch(
            f"{self.URL}/{self.template.id}", {"folderId": "nope"}, format="json"
        )
        self.assertEqual(response.status_code, 404)

    def test_another_teachers_template_cannot_be_edited(self):
        other = User.objects.create(email="o@example.com", name="O", status="approved")
        theirs = PaperTemplate.objects.create(
            user=other, name="Theirs", instructions="x"
        )
        response = self.client.patch(
            f"{self.URL}/{theirs.id}", {"name": "Mine now"}, format="json"
        )
        self.assertEqual(response.status_code, 404)
        theirs.refresh_from_db()
        self.assertEqual(theirs.name, "Theirs")

    def test_renaming_onto_an_existing_name_is_refused(self):
        PaperTemplate.objects.create(
            user=self.user, name="Taken", instructions="x"
        )
        response = self.client.patch(
            f"{self.URL}/{self.template.id}", {"name": "Taken"}, format="json"
        )
        self.assertEqual(response.status_code, 400)


class PaperTemplateForkTests(DesignApiTestCase):
    """A built-in is generated code; forking is where it becomes data."""

    URL = "/api/generation/templates/fork"

    def _blueprint(self):
        from services.templates import SlotSpec, TemplateBlueprint

        return TemplateBlueprint(
            slots=[
                SlotSpec(
                    index=0,
                    section_title="Section A",
                    question_type="MCQ",
                    marks=1,
                )
            ]
        )

    def test_forking_a_builtin_writes_an_owned_pinned_row(self):
        with patch(
            "services.template_catalog.resolve_builtin",
            return_value=self._blueprint(),
        ):
            response = self.client.post(
                self.URL, {"templateId": "cbse-science-10"}, format="json"
            )

        self.assertEqual(response.status_code, 201)
        body = response.json()["template"]
        self.assertTrue(body["pinned"], "a fork keeps the structure it showed")
        self.assertFalse(body["builtin"])
        self.assertEqual(body["base_template_id"], "cbse-science-10")
        self.assertEqual(PaperTemplate.objects.filter(user=self.user).count(), 1)

    def test_forking_the_same_builtin_twice_suffixes_rather_than_failing(self):
        """The unique-name constraint is right for a deliberate save and wrong
        here: the teacher never typed this name."""
        with patch(
            "services.template_catalog.resolve_builtin",
            return_value=self._blueprint(),
        ):
            first = self.client.post(
                self.URL, {"templateId": "cbse-science-10"}, format="json"
            )
            second = self.client.post(
                self.URL, {"templateId": "cbse-science-10"}, format="json"
            )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(
            first.json()["template"]["name"], second.json()["template"]["name"]
        )
        self.assertEqual(PaperTemplate.objects.filter(user=self.user).count(), 2)

    def test_forking_into_a_folder(self):
        folder = TemplateFolder.objects.create(user=self.user, name="Term 1")
        with patch(
            "services.template_catalog.resolve_builtin",
            return_value=self._blueprint(),
        ):
            response = self.client.post(
                self.URL,
                {"templateId": "cbse-science-10", "folderId": folder.id},
                format="json",
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["template"]["folderId"], folder.id)

    def test_an_unknown_catalog_id_is_a_404(self):
        response = self.client.post(
            self.URL, {"templateId": "not-a-template"}, format="json"
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(PaperTemplate.objects.count(), 0)

    def test_forking_describe_it_yourself_with_nothing_said_is_refused(self):
        """It resolves to no slots until the teacher describes something, and a
        row with neither slots nor prose cannot rebuild a paper."""
        from services.templates import TemplateBlueprint

        with patch(
            "services.template_catalog.resolve_builtin",
            return_value=TemplateBlueprint(slots=[]),
        ):
            response = self.client.post(
                self.URL, {"templateId": "describe-it-yourself"}, format="json"
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(PaperTemplate.objects.count(), 0)


class PaperTemplateDuplicateTests(DesignApiTestCase):
    def setUp(self):
        super().setUp()
        self.template = PaperTemplate.objects.create(
            user=self.user,
            name="Weekly",
            instructions="3 MCQ",
            settings={"difficulty": "medium"},
            source_config={"mode": "bank"},
            last_used_at=timezone.now(),
        )

    def test_a_duplicate_copies_the_recipe_under_a_free_name(self):
        response = self.client.post(
            f"/api/generation/templates/{self.template.id}/duplicate", format="json"
        )
        self.assertEqual(response.status_code, 201)

        copy = response.json()["template"]
        self.assertNotEqual(copy["name"], "Weekly")
        self.assertEqual(copy["instructions"], "3 MCQ")
        self.assertEqual(copy["settings"]["difficulty"], "medium")
        self.assertEqual(copy["source_config"]["mode"], "bank")

    def test_a_duplicate_starts_unused(self):
        """Otherwise a copy made to experiment with immediately outranks the
        template it came from in the picker."""
        response = self.client.post(
            f"/api/generation/templates/{self.template.id}/duplicate", format="json"
        )
        self.assertIsNone(response.json()["template"]["last_used_at"])

    def test_another_teachers_template_cannot_be_duplicated(self):
        other = User.objects.create(email="o@example.com", name="O", status="approved")
        theirs = PaperTemplate.objects.create(
            user=other, name="Theirs", instructions="x"
        )
        response = self.client.post(
            f"/api/generation/templates/{theirs.id}/duplicate", format="json"
        )
        self.assertEqual(response.status_code, 404)
