"""Questions from a teacher's own image: the bytes, the edits, the prompt, the originals."""

import base64
import json
import struct
import zlib
from types import SimpleNamespace
from unittest.mock import patch

import fitz  # PyMuPDF: builds real JPEG/PNG bytes without a new dependency
from django.test import SimpleTestCase, override_settings

from services.generation import image_question as I


# ── Fixtures ────────────────────────────────────────────────────────────

def png(width=120, height=80):
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))

    def chunk(kind, data):
        body = struct.pack(">I", len(data)) + kind + data
        return body + struct.pack(">I", zlib.crc32(kind + data))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def jpeg(width=96, height=64):
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, width, height), False)
    pix.clear_with(200)
    return pix.tobytes("jpeg")


GIF_1X1 = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
WEBP_1X1 = base64.b64decode("UklGRhoAAABXRUJQVlA4TA0AAAAvAAAAEAcQERGIiP4HAA==")


class FakeStorage:
    """Stands in for default_storage; records what was saved."""

    def __init__(self):
        self.files = {}

    def exists(self, path):
        return path in self.files

    def save(self, path, content):
        self.files[path] = content.read()
        return path


def a_user(uid="u1"):
    return SimpleNamespace(id=uid)


GOOD = {
    "understanding": {"summary": "A series circuit with a 6 V battery and two resistors.", "kind": "diagram",
                       "elements": ["battery", "R1", "R2"], "concerns": []},
    "alt_text": "A series circuit with a battery and two resistors",
    "question": {
        "type": "SHORT_ANSWER",
        "question": "In the circuit shown, find the total resistance if R1 = 2 ohm and R2 = 4 ohm.",
        "options": [], "answer": "6 ohm", "explanation": "Series: R = R1 + R2.",
        "marks": 2, "topic": "Series circuits", "blooms": "APPLY", "difficulty": "easy",
    },
}


def stub_client(*payloads):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        body = payloads[min(len(calls) - 1, len(payloads) - 1)]
        text = body if isinstance(body, str) else json.dumps(body)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason="stop")], usage=None
        )

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return client, calls


def run(payload=GOOD, **kwargs):
    client, calls = stub_client(payload)
    storage = FakeStorage()
    args = dict(user=a_user(), image=png())
    args.update(kwargs)
    with patch.object(I, "get_openai_client", return_value=client), \
         patch.object(I, "_record_usage") as usage, \
         patch.object(I, "default_storage", storage):
        result = I.generate_image_question(**args)
    return result, calls, storage, usage


# ── Looking at the bytes ────────────────────────────────────────────────

class InspectTests(SimpleTestCase):
    def test_each_format_is_recognised_by_its_bytes_and_measured(self):
        info = I.inspect_image(png(120, 80))
        self.assertEqual((info.content_type, info.extension, info.width, info.height), ("image/png", "png", 120, 80))
        info = I.inspect_image(jpeg(96, 64))
        self.assertEqual((info.content_type, info.extension, info.width, info.height), ("image/jpeg", "jpg", 96, 64))

    def test_gif_and_webp_headers_are_read(self):
        self.assertEqual(I.sniff_type(GIF_1X1), "image/gif")
        self.assertEqual(I._dimensions(GIF_1X1, "image/gif"), (1, 1))
        self.assertEqual(I.sniff_type(WEBP_1X1), "image/webp")
        self.assertEqual(I._dimensions(WEBP_1X1, "image/webp"), (1, 1))

    def test_a_name_or_claimed_type_is_not_trusted_only_the_bytes(self):
        for fake in (b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",
                     b"<html><body>hi</body></html>", b"%PDF-1.7 not an image", b"x" * 200):
            with self.assertRaisesRegex(I.ImageQuestionError, "not a PNG, JPEG, WebP or GIF"):
                I.inspect_image(fake)

    def test_svg_is_never_accepted(self):
        self.assertNotIn("image/svg+xml", I.ALLOWED_TYPES)

    def test_an_empty_file_is_refused(self):
        with self.assertRaisesRegex(I.ImageQuestionError, "empty"):
            I.inspect_image(b"")

    def test_an_oversized_file_is_refused_with_its_size(self):
        with self.assertRaisesRegex(I.ImageQuestionError, r"MB"):
            I.inspect_image(png() + b"\x00" * (I.MAX_IMAGE_BYTES + 1))

    def test_a_damaged_header_is_refused_not_crashed_on(self):
        with self.assertRaisesRegex(I.ImageQuestionError, "damaged"):
            I.inspect_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 10)
        with self.assertRaisesRegex(I.ImageQuestionError, "damaged"):
            I.inspect_image(b"\xff\xd8\xff\xe0")

    def test_a_thumbnail_and_a_billboard_are_refused(self):
        with self.assertRaisesRegex(I.ImageQuestionError, "too small"):
            I.inspect_image(GIF_1X1)
        with self.assertRaisesRegex(I.ImageQuestionError, "too large"):
            I.inspect_image(png(I.MAX_SIDE + 1, 30))

    def test_identical_bytes_have_the_same_hash(self):
        self.assertEqual(I.inspect_image(png()).sha256, I.inspect_image(png()).sha256)
        self.assertNotEqual(I.inspect_image(png(120, 80)).sha256, I.inspect_image(png(121, 80)).sha256)


# ── Edits ───────────────────────────────────────────────────────────────

class SanitizeEditsTests(SimpleTestCase):
    def test_valid_edits_pass_through_with_defaults_filled_in(self):
        out = I.sanitize_edits([
            {"op": "highlight", "x": 0.1, "y": 0.2, "w": 0.3, "h": 0.1},
            {"op": "arrow", "x1": 0.1, "y1": 0.1, "x2": 0.5, "y2": 0.5},
            {"op": "label", "x": 0.4, "y": 0.4, "text": "R2"},
            {"op": "cover", "x": 0.0, "y": 0.0, "w": 0.2, "h": 0.2},
            {"op": "crop", "x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8},
        ])
        self.assertEqual([e["op"] for e in out], ["highlight", "arrow", "label", "cover", "crop"])
        self.assertEqual(out[0]["color"], "#ffd400")
        self.assertEqual(out[1]["color"], "#e11d48")
        self.assertNotIn("color", out[3])

    def test_coordinates_are_clamped_to_the_picture(self):
        (e,) = I.sanitize_edits([{"op": "box", "x": -0.5, "y": 0.9, "w": 3, "h": 3}])
        self.assertEqual((e["x"], e["y"]), (0.0, 0.9))
        self.assertLessEqual(e["x"] + e["w"], 1.0)
        self.assertLessEqual(e["y"] + e["h"], 1.0)

    def test_nonsense_is_dropped_never_raised(self):
        junk = [
            "text", None, 3, {}, {"op": "explode"}, {"op": "box"}, {"op": "box", "x": "a", "y": 0, "w": 1, "h": 1},
            {"op": "box", "x": 0.5, "y": 0.5, "w": 0, "h": 0.5},                     # no area
            {"op": "box", "x": float("nan"), "y": 0, "w": 0.5, "h": 0.5},
            {"op": "arrow", "x1": 0.5, "y1": 0.5, "x2": 0.5, "y2": 0.5},             # no length
            {"op": "label", "x": 0.5, "y": 0.5, "text": "   "},
        ]
        self.assertEqual(I.sanitize_edits(junk), [])
        self.assertEqual(I.sanitize_edits("not a list"), [])
        self.assertEqual(I.sanitize_edits(None), [])

    def test_a_colour_must_be_a_plain_hex_value(self):
        (e,) = I.sanitize_edits([{"op": "box", "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2, "color": "url(javascript:alert(1))"}])
        self.assertEqual(e["color"], "#e11d48")
        (e,) = I.sanitize_edits([{"op": "box", "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2, "color": "#00aa00"}])
        self.assertEqual(e["color"], "#00aa00")

    def test_labels_are_trimmed_and_capped(self):
        (e,) = I.sanitize_edits([{"op": "label", "x": 0.1, "y": 0.1, "text": "  a   b  " + "z" * 200}])
        self.assertTrue(e["text"].startswith("a b "))
        self.assertLessEqual(len(e["text"]), I.MAX_LABEL_CHARS)

    def test_only_the_last_crop_counts(self):
        out = I.sanitize_edits([
            {"op": "crop", "x": 0.0, "y": 0.0, "w": 0.5, "h": 0.5},
            {"op": "box", "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.2},
            {"op": "crop", "x": 0.2, "y": 0.2, "w": 0.5, "h": 0.5},
        ])
        crops = [e for e in out if e["op"] == "crop"]
        self.assertEqual(len(crops), 1)
        self.assertEqual(crops[0]["x"], 0.2)

    def test_the_number_of_edits_is_bounded(self):
        many = [{"op": "box", "x": 0.1, "y": 0.1, "w": 0.1, "h": 0.1}] * 100
        self.assertEqual(len(I.sanitize_edits(many)), I.MAX_EDITS)


class DescribeEditsTests(SimpleTestCase):
    def test_a_covered_part_is_marked_off_limits(self):
        (line,) = I.describe_edits([{"op": "cover", "x": 0.0, "y": 0.0, "w": 0.2, "h": 0.2}])
        self.assertIn("covered", line)
        self.assertIn("do not ask about", line)
        self.assertIn("upper-left", line)

    def test_each_edit_is_described_with_where_it_is(self):
        lines = I.describe_edits(I.sanitize_edits([
            {"op": "highlight", "x": 0.7, "y": 0.7, "w": 0.2, "h": 0.2},
            {"op": "label", "x": 0.5, "y": 0.5, "text": "θ"},
            {"op": "arrow", "x1": 0.1, "y1": 0.1, "x2": 0.8, "y2": 0.2},
            {"op": "crop", "x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8},
        ]))
        joined = " ".join(lines)
        self.assertIn("lower-right", joined)
        self.assertIn("“θ”", joined)
        self.assertIn("upper-right", joined)
        self.assertIn("cropped", joined)

    def test_no_edits_say_nothing(self):
        self.assertEqual(I.describe_edits([]), [])


# ── What the model is told ──────────────────────────────────────────────

class PromptTests(SimpleTestCase):
    def messages(self, **kwargs):
        base = dict(image=png(), content_type="image/png", description="", instructions="", edits=[],
                    subject="Science", class_num=10, question_type="", marks=None, difficulty="")
        base.update(kwargs)
        return I.build_generation_messages(**base)

    @staticmethod
    def text(messages):
        return messages[1]["content"][0]["text"]

    def test_the_image_travels_as_a_data_url_at_high_detail(self):
        part = self.messages()[1]["content"][1]
        self.assertEqual(part["type"], "image_url")
        self.assertTrue(part["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(part["image_url"]["detail"], "high")

    def test_the_teachers_description_and_instructions_are_passed_verbatim(self):
        text = self.text(self.messages(description="A velocity-time graph of a lift.",
                                       instructions="Ask about the distance in the first 4 seconds."))
        self.assertIn("A velocity-time graph of a lift.", text)
        self.assertIn("Ask about the distance in the first 4 seconds.", text)

    def test_the_system_prompt_gives_the_teachers_words_priority(self):
        system = self.messages()[0]["content"]
        self.assertIn("Treat it as true", system)
        self.assertIn("over your own reading", system)
        self.assertIn("take priority over your own choice", system)

    def test_without_words_the_model_is_told_to_work_it_out(self):
        text = self.text(self.messages())
        self.assertIn("none given — work out what the image shows", text)
        self.assertIn("none given — choose a sensible focus", text)
        self.assertIn("your choice", text)

    def test_the_request_can_name_type_marks_and_difficulty(self):
        text = self.text(self.messages(question_type="NUMERICAL", marks=3, difficulty="hard", class_num=9))
        for needle in ("Question type: NUMERICAL", "Marks: 3", "Difficulty: hard", "Class: 9"):
            self.assertIn(needle, text)

    def test_edits_are_explained_so_the_model_knows_what_it_sees(self):
        text = self.text(self.messages(edits=I.sanitize_edits([
            {"op": "cover", "x": 0.0, "y": 0.0, "w": 0.2, "h": 0.2},
            {"op": "highlight", "x": 0.6, "y": 0.6, "w": 0.2, "h": 0.2},
        ])))
        self.assertIn("WHAT WAS DONE TO THE PICTURE", text)
        self.assertIn("do not ask about what was there", text)
        self.assertIn("highlighted", text)

    def test_no_edits_means_no_edit_section(self):
        self.assertNotIn("WHAT WAS DONE", self.text(self.messages()))

    def test_the_figure_may_be_referred_to_unlike_the_chapter_pipelines_rule(self):
        self.assertIn("may refer to it", self.messages()[0]["content"])

    def test_maths_and_json_escaping_are_covered(self):
        system = self.messages()[0]["content"]
        self.assertIn("\\( … \\)", system)
        self.assertIn("doubled", system)

    def test_the_syllabus_and_exactness_rules_are_there(self):
        system = self.messages()[0]["content"]
        self.assertIn("inside the class's syllabus", system)
        self.assertIn("never invent a number", system)


# ── The whole thing, with a stub model ──────────────────────────────────

class GenerateTests(SimpleTestCase):
    def test_a_question_comes_back_in_the_editors_shape_carrying_the_picture(self):
        result, _, _, _ = run(description="A series circuit.")
        q = result["question"]
        self.assertEqual(q["type"], "SHORT_ANSWER")
        self.assertIn("In the circuit shown", q["content"])
        self.assertEqual((q["marks"], q["answer"]), (2, "6 ohm"))
        self.assertTrue(q["image_url"].startswith("/media/user_images/u1/") or "user_images/u1/" in q["image_url"])
        self.assertEqual(q["image_alt"], "A series circuit with a battery and two resistors")
        self.assertEqual(q["metadata"]["sourceType"], "image")
        self.assertTrue(q["metadata"]["imageQuestion"])
        self.assertEqual(q["metadata"]["difficulty"], "easy")

    def test_what_the_model_understood_is_returned_for_the_teacher_to_check(self):
        result, _, _, _ = run()
        u = result["understanding"]
        self.assertIn("series circuit", u["summary"])
        self.assertEqual((u["kind"], u["elements"]), ("diagram", ["battery", "R1", "R2"]))

    def test_it_works_with_no_description_and_no_instructions(self):
        result, calls, _, _ = run()
        self.assertFalse(result["usedDescription"])
        self.assertFalse(result["usedInstructions"])
        self.assertIn("none given", calls[0]["messages"][1]["content"][0]["text"])

    def test_the_teachers_words_reach_the_model_and_are_reported_as_used(self):
        result, calls, _, _ = run(description="Ohm's law apparatus", instructions="Ask for R1")
        self.assertTrue(result["usedDescription"] and result["usedInstructions"])
        text = calls[0]["messages"][1]["content"][0]["text"]
        self.assertIn("Ohm's law apparatus", text)
        self.assertIn("Ask for R1", text)

    def test_a_requested_type_and_marks_are_enforced_whatever_the_model_wrote(self):
        result, _, _, _ = run(question_type="LONG_ANSWER", marks=5)
        self.assertEqual((result["question"]["type"], result["question"]["marks"]), ("LONG_ANSWER", 5))

    def test_an_unknown_type_or_silly_marks_are_ignored(self):
        result, calls, _, _ = run(question_type="BANANA", marks=999)
        text = calls[0]["messages"][1]["content"][0]["text"]
        self.assertIn("your choice", text)
        self.assertEqual(result["question"]["marks"], 2)  # the model's own

    def test_the_original_is_stored_untouched_when_there_are_no_edits(self):
        original = png(200, 150)
        result, _, storage, _ = run(image=original)
        self.assertEqual(len(storage.files), 1)
        (stored,) = storage.files.values()
        self.assertEqual(stored, original)
        self.assertFalse(result["image"]["edited"])
        self.assertEqual(result["image"]["url"], result["image"]["originalUrl"])

    def test_an_edited_picture_is_stored_beside_the_unchanged_original(self):
        original, edited = png(200, 150), png(120, 90)
        result, _, storage, _ = run(
            image=edited, original=original,
            edits=[{"op": "crop", "x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5}],
        )
        self.assertEqual(len(storage.files), 2)
        self.assertIn(original, storage.files.values())
        self.assertIn(edited, storage.files.values())
        self.assertTrue(result["image"]["edited"])
        self.assertNotEqual(result["image"]["url"], result["image"]["originalUrl"])
        self.assertEqual(result["question"]["image_url"], result["image"]["url"])
        self.assertEqual(result["question"]["metadata"]["originalImageUrl"], result["image"]["originalUrl"])
        self.assertEqual(len(result["image"]["edits"]), 1)

    def test_the_model_is_shown_the_edited_picture_not_the_original(self):
        original, edited = png(200, 150), png(120, 90)
        _, calls, _, _ = run(image=edited, original=original,
                             edits=[{"op": "cover", "x": 0.0, "y": 0.0, "w": 0.2, "h": 0.2}])
        sent = calls[0]["messages"][1]["content"][1]["image_url"]["url"]
        self.assertEqual(sent, "data:image/png;base64," + base64.b64encode(edited).decode())
        self.assertIn("covered", calls[0]["messages"][1]["content"][0]["text"])

    def test_the_same_picture_twice_is_stored_once(self):
        _, _, storage, _ = run()
        self.assertEqual(len(storage.files), 1)

    def test_pictures_are_kept_per_user(self):
        a = run(user=a_user("alice"))[2]
        b = run(user=a_user("bob"))[2]
        self.assertTrue(all("/alice/" in k for k in a.files))
        self.assertTrue(all("/bob/" in k for k in b.files))

    def test_usage_is_billed_to_the_user_under_its_own_operation(self):
        _, _, _, usage = run()
        usage.assert_called_once()
        self.assertEqual(usage.call_args.args[1], "image_question")

    def test_a_bad_file_never_reaches_the_model(self):
        client, calls = stub_client(GOOD)
        with patch.object(I, "get_openai_client", return_value=client), patch.object(I, "default_storage", FakeStorage()):
            with self.assertRaises(I.ImageQuestionError):
                I.generate_image_question(user=a_user(), image=b"not an image at all, sorry" * 4)
        self.assertEqual(calls, [])

    def test_latex_in_the_question_is_cleaned_like_any_generated_question(self):
        payload = {**GOOD, "question": {**GOOD["question"], "question": "Find \\frac{1}{2} of the length."}}
        result, _, _, _ = run(payload)
        self.assertIn("\\(\\frac{1}{2}\\)", result["question"]["content"])

    def test_single_backslashes_in_the_reply_are_tolerated(self):
        raw = '{"question": {"type": "SHORT_ANSWER", "question": "Find \\(x\\) here.", "answer": "2", "marks": 1, "topic": "t", "blooms": "APPLY", "difficulty": "easy"}}'
        result, _, _, _ = run(raw)
        self.assertIn("\\(x\\)", result["question"]["content"])

    def test_a_fenced_reply_is_read(self):
        result, _, _, _ = run("```json\n" + json.dumps(GOOD) + "\n```")
        self.assertIn("In the circuit shown", result["question"]["content"])

    def test_a_reply_with_no_question_is_a_provider_error_to_retry(self):
        with self.assertRaises(I.ImageProviderError):
            run({"understanding": {"summary": "x"}})

    def test_junk_is_a_provider_error_not_a_crash(self):
        with self.assertRaises(I.ImageProviderError):
            run("sorry, I cannot help with that")

    def test_an_incomplete_question_is_a_provider_error(self):
        with self.assertRaises(I.ImageProviderError):
            run({"question": {"type": "SHORT_ANSWER", "question": "", "answer": "x", "marks": 1}})

    def test_a_model_failure_is_a_provider_error_with_a_teacher_message(self):
        class Boom:
            chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **k: (_ for _ in ()).throw(RuntimeError("rate limited"))))

        with patch.object(I, "get_openai_client", return_value=Boom()), patch.object(I, "default_storage", FakeStorage()):
            with self.assertRaisesRegex(I.ImageProviderError, "Try again"):
                I.generate_image_question(user=a_user(), image=png())

    def test_nothing_is_stored_when_the_model_fails(self):
        storage = FakeStorage()

        class Boom:
            chat = SimpleNamespace(completions=SimpleNamespace(create=lambda **k: (_ for _ in ()).throw(RuntimeError("x"))))

        with patch.object(I, "get_openai_client", return_value=Boom()), patch.object(I, "default_storage", storage):
            with self.assertRaises(I.ImageProviderError):
                I.generate_image_question(user=a_user(), image=png())
        self.assertEqual(storage.files, {})

    @override_settings(IMAGE_QUESTION_MODEL="gpt-4o")
    def test_the_model_is_configurable(self):
        _, calls, _, _ = run()
        self.assertEqual(calls[0]["model"], "gpt-4o")
        self.assertEqual(calls[0]["response_format"], {"type": "json_object"})

    @override_settings(IMAGE_QUESTION_MODEL=None, OPENAI_VISION_MODEL="gpt-4.1-mini")
    def test_it_falls_back_to_the_vision_model(self):
        _, calls, _, _ = run()
        self.assertEqual(calls[0]["model"], "gpt-4.1-mini")

    @override_settings(IMAGE_QUESTION_MODEL="gpt-5-mini")
    def test_reasoning_models_get_a_low_effort_setting(self):
        _, calls, _, _ = run()
        self.assertEqual(calls[0]["reasoning_effort"], "low")


class StoreImagesTests(SimpleTestCase):
    def test_storing_without_a_model_keeps_the_original(self):
        storage = FakeStorage()
        original = png(100, 100)
        with patch.object(I, "default_storage", storage):
            out = I.store_images(a_user(), image=original)
        self.assertEqual(list(storage.files.values()), [original])
        self.assertFalse(out["edited"])
        self.assertEqual((out["width"], out["height"]), (100, 100))

    def test_an_invalid_original_is_refused_too(self):
        with patch.object(I, "default_storage", FakeStorage()):
            with self.assertRaises(I.ImageQuestionError):
                I.store_images(a_user(), image=png(100, 100), original=b"junk" * 20)

    def test_a_storage_failure_is_a_provider_error(self):
        class Broken(FakeStorage):
            def save(self, path, content):
                raise OSError("disk full")

        with patch.object(I, "default_storage", Broken()):
            with self.assertRaises(I.ImageProviderError):
                I.store_images(a_user(), image=png())


# ── Suggesting edits ────────────────────────────────────────────────────

class PlanEditsTests(SimpleTestCase):
    PLAN = {
        "edits": [
            {"op": "crop", "x": 0.1, "y": 0.1, "w": 0.7, "h": 0.7},
            {"op": "highlight", "x": 0.3, "y": 0.3, "w": 0.1, "h": 0.1},
            {"op": "explode", "x": 0, "y": 0},
        ],
        "notes": ["Crop to the circuit", "Highlight R2"],
        "unsupported": ["Make the battery bigger"],
    }

    def plan(self, payload=PLAN, **kwargs):
        client, calls = stub_client(payload)
        args = dict(user=a_user(), image=png(), instruction="crop to the circuit and highlight R2")
        args.update(kwargs)
        with patch.object(I, "get_openai_client", return_value=client), patch.object(I, "_record_usage") as usage:
            return I.plan_image_edits(**args), calls, usage

    def test_the_proposal_is_sanitised_and_keeps_the_models_own_caveats(self):
        out, _, _ = self.plan()
        self.assertEqual([e["op"] for e in out["edits"]], ["crop", "highlight"])
        self.assertEqual(out["notes"], ["Crop to the circuit", "Highlight R2"])
        self.assertEqual(out["unsupported"], ["Make the battery bigger"])

    def test_the_teachers_request_and_description_reach_the_model(self):
        _, calls, _ = self.plan(description="A series circuit")
        text = calls[0]["messages"][1]["content"][0]["text"]
        self.assertIn("crop to the circuit and highlight R2", text)
        self.assertIn("A series circuit", text)

    def test_the_prompt_forbids_touching_what_was_not_mentioned_and_repainting(self):
        _, calls, _ = self.plan()
        system = calls[0]["messages"][0]["content"]
        self.assertIn("nothing more", system)
        self.assertIn("cannot redraw", system)
        self.assertIn("unsupported", system)
        self.assertIn("TOP-LEFT", system)

    def test_an_empty_request_is_refused_without_a_model_call(self):
        client, calls = stub_client(self.PLAN)
        with patch.object(I, "get_openai_client", return_value=client):
            with self.assertRaisesRegex(I.ImageQuestionError, "Say what you want changed"):
                I.plan_image_edits(user=a_user(), image=png(), instruction="   ")
        self.assertEqual(calls, [])

    def test_usage_is_billed_under_its_own_operation(self):
        _, _, usage = self.plan()
        self.assertEqual(usage.call_args.args[1], "image_edit_plan")

    def test_the_picture_is_not_stored_by_planning(self):
        storage = FakeStorage()
        client, _ = stub_client(self.PLAN)
        with patch.object(I, "get_openai_client", return_value=client), patch.object(I, "_record_usage"), \
             patch.object(I, "default_storage", storage):
            I.plan_image_edits(user=a_user(), image=png(), instruction="crop it")
        self.assertEqual(storage.files, {})
