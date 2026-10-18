"""The image-question endpoints: auth, multipart parsing, and the two failure kinds."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from services.generation import image_question as I
from services.generation.tests.test_image_question import GOOD, FakeStorage, png, stub_client
from services.organizations.usage_limits import UsageLimitExceeded


def upload(name="figure.png", data=None, content_type="image/png"):
    return SimpleUploadedFile(name, data if data is not None else png(), content_type=content_type)


class ImageApiTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create(email="img@example.com", name="Img", status="approved")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.storage = FakeStorage()
        patches = [
            patch.object(I, "default_storage", self.storage),
            patch.object(I, "_record_usage"),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def model(self, *payloads):
        client, calls = stub_client(*payloads)
        patcher = patch.object(I, "get_openai_client", return_value=client)
        patcher.start()
        self.addCleanup(patcher.stop)
        return calls


class ImageQuestionApiTests(ImageApiTestCase):
    URL = "/api/generation/image-question"

    def test_the_dialog_can_list_the_question_types(self):
        body = self.client.get(self.URL).json()
        values = [t["value"] for t in body["types"]]
        self.assertEqual(values[0], "")  # "let the AI choose" comes first
        self.assertIn("MCQ", values)

    def test_a_multipart_upload_with_words_returns_a_question_carrying_the_picture(self):
        calls = self.model(GOOD)
        response = self.client.post(
            self.URL,
            {"image": upload(), "description": "A circuit", "instructions": "Ask for the total resistance",
             "subject": "Science", "class": "10", "questionType": "SHORT_ANSWER", "marks": "2"},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertIn("In the circuit shown", body["question"]["content"])
        self.assertTrue(body["question"]["image_url"])
        self.assertTrue(body["usedDescription"] and body["usedInstructions"])
        text = calls[0]["messages"][1]["content"][0]["text"]
        self.assertIn("A circuit", text)
        self.assertIn("Subject: Science | Class: 10", text)

    def test_no_words_at_all_is_a_normal_request(self):
        self.model(GOOD)
        response = self.client.post(self.URL, {"image": upload()}, format="multipart")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["usedDescription"])

    def test_an_edited_picture_and_its_original_are_both_kept(self):
        self.model(GOOD)
        original, edited = png(200, 150), png(100, 75)
        response = self.client.post(
            self.URL,
            {"image": upload("edited.png", edited), "original": upload("orig.png", original),
             "edits": json.dumps([{"op": "crop", "x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5}])},
            format="multipart",
        )
        self.assertEqual(response.status_code, 200, response.content)
        image = response.json()["image"]
        self.assertTrue(image["edited"])
        self.assertNotEqual(image["url"], image["originalUrl"])
        self.assertIn(original, self.storage.files.values())
        self.assertIn(edited, self.storage.files.values())

    def test_edits_that_are_not_json_are_ignored_not_fatal(self):
        self.model(GOOD)
        response = self.client.post(self.URL, {"image": upload(), "edits": "{{not json"}, format="multipart")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["image"]["edited"])

    def test_no_image_is_a_400_with_a_reason(self):
        response = self.client.post(self.URL, {"description": "hi"}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Choose an image", response.json()["error"])

    def test_a_file_that_is_not_an_image_is_a_400_and_costs_nothing(self):
        calls = self.model(GOOD)
        fake = upload("evil.png", b"<svg><script>alert(1)</script></svg>" * 3)
        response = self.client.post(self.URL, {"image": fake}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("not a PNG, JPEG, WebP or GIF", response.json()["error"])
        self.assertEqual(calls, [])
        self.assertEqual(self.storage.files, {})

    def test_an_oversized_upload_is_refused_before_it_is_read(self):
        calls = self.model(GOOD)
        big = upload("big.png", png() + b"\x00" * (I.MAX_IMAGE_BYTES + 10))
        response = self.client.post(self.URL, {"image": big}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertIn("MB", response.json()["error"])
        self.assertEqual(calls, [])

    def test_the_monthly_limit_is_a_402_with_its_own_payload(self):
        calls = self.model(GOOD)
        exc = UsageLimitExceeded(organization_id="o1", organization_name="School", limit=1000, used=1000)
        with patch("apps.generation.image_views.check_monthly_token_limit", side_effect=exc):
            response = self.client.post(self.URL, {"image": upload()}, format="multipart")
        self.assertEqual(response.status_code, 402)
        self.assertEqual(response.json()["code"], "ORG_TOKEN_LIMIT_EXCEEDED")
        self.assertEqual(calls, [])

    def test_a_model_failure_is_a_502_worth_retrying(self):
        self.model("sorry, no")
        response = self.client.post(self.URL, {"image": upload()}, format="multipart")
        self.assertEqual(response.status_code, 502)
        self.assertIn("error", response.json())

    def test_an_anonymous_caller_is_refused(self):
        self.model(GOOD)
        response = APIClient().post(self.URL, {"image": upload()}, format="multipart")
        self.assertIn(response.status_code, (401, 403))

    def test_the_wire_shape_matches_what_the_editor_inserts(self):
        self.model(GOOD)
        question = self.client.post(self.URL, {"image": upload()}, format="multipart").json()["question"]
        for key in ("content", "type", "options", "answer", "marks", "image_url", "metadata"):
            self.assertIn(key, question)


class EditPlanApiTests(ImageApiTestCase):
    URL = "/api/generation/image-edit-plan"
    PLAN = {"edits": [{"op": "highlight", "x": 0.3, "y": 0.3, "w": 0.2, "h": 0.2}], "notes": ["Highlight R2"], "unsupported": []}

    def test_a_request_in_words_becomes_edits_to_review(self):
        calls = self.model(self.PLAN)
        response = self.client.post(self.URL, {"image": upload(), "instruction": "highlight R2"}, format="multipart")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["edits"][0]["op"], "highlight")
        self.assertIn("highlight R2", calls[0]["messages"][1]["content"][0]["text"])

    def test_planning_stores_nothing(self):
        self.model(self.PLAN)
        self.client.post(self.URL, {"image": upload(), "instruction": "highlight R2"}, format="multipart")
        self.assertEqual(self.storage.files, {})

    def test_an_empty_instruction_is_a_400(self):
        calls = self.model(self.PLAN)
        response = self.client.post(self.URL, {"image": upload(), "instruction": " "}, format="multipart")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(calls, [])

    def test_no_image_is_a_400(self):
        response = self.client.post(self.URL, {"instruction": "crop"}, format="multipart")
        self.assertEqual(response.status_code, 400)


class ImageUploadApiTests(ImageApiTestCase):
    URL = "/api/generation/image-upload"

    def test_a_picture_is_stored_for_an_existing_question_without_any_model(self):
        calls = self.model(GOOD)
        response = self.client.post(self.URL, {"image": upload(), "description": "Ray diagram of a lens"}, format="multipart")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["url"])
        self.assertEqual(body["alt"], "Ray diagram of a lens")
        self.assertFalse(body["edited"])
        self.assertEqual(calls, [])

    def test_the_original_is_kept_when_the_picture_was_edited(self):
        original, edited = png(300, 200), png(150, 100)
        response = self.client.post(
            self.URL,
            {"image": upload("e.png", edited), "original": upload("o.png", original),
             "edits": json.dumps([{"op": "crop", "x": 0, "y": 0, "w": 0.5, "h": 0.5}])},
            format="multipart",
        )
        body = response.json()
        self.assertTrue(body["edited"])
        self.assertNotEqual(body["url"], body["originalUrl"])
        self.assertEqual(sorted(self.storage.files.values(), key=len), sorted([original, edited], key=len))

    def test_a_non_image_is_a_400(self):
        response = self.client.post(self.URL, {"image": upload("x.png", b"hello hello hello hello")}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_alt_text_is_trimmed(self):
        response = self.client.post(self.URL, {"image": upload(), "description": "a " * 300}, format="multipart")
        self.assertLessEqual(len(response.json()["alt"]), 200)
