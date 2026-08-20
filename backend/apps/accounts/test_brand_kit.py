"""Tests for the brand kit — a school's identity, stored once.

The properties worth pinning down are all about what the kit must NEVER do. It
must never be the reason a paper cannot be printed, so every field is optional
and an empty kit is a valid kit. It must never hand out a URL that expires,
because a saved paper outlives any signed link. And one school's crest must
never be reachable, renameable or deletable from another account.
"""

from __future__ import annotations

import base64
import struct
import zlib

from django.core.files.storage import default_storage
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import BrandAsset, BrandKit, User
from services.brand_kit import _image_dimensions


def a_png(width: int = 8, height: int = 4) -> bytes:
    """A real, decodable PNG of a stated size."""
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def an_upload(data: bytes, name: str = "crest.png", content_type: str = "image/png"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, data, content_type=content_type)


class BrandKitTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create(email="t@example.com", name="T", status="approved")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)


class ImageDimensionTests(TestCase):
    """Parsed from the file header rather than with an imaging library, so the
    formats have to be covered explicitly."""

    def test_png_dimensions_are_read(self):
        self.assertEqual(_image_dimensions(a_png(200, 37)), (200, 37))

    def test_gif_dimensions_are_read(self):
        gif = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")
        self.assertEqual(_image_dimensions(gif), (1, 1))

    def test_jpeg_dimensions_are_read(self):
        jpg = base64.b64decode(
            "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof"
            "Hh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAAB"
            "AAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q=="
        )
        self.assertEqual(_image_dimensions(jpg), (1, 1))

    def test_an_unmeasurable_file_is_not_an_error(self):
        """A logo we cannot measure is still a perfectly good logo."""
        self.assertEqual(_image_dimensions(b"not an image"), (None, None))
        self.assertEqual(_image_dimensions(b""), (None, None))


class BrandKitApiTests(BrandKitTestCase):
    URL = "/api/auth/brand-kit"

    def test_reading_creates_an_empty_kit(self):
        """The client never has to tell "no kit yet" from "an empty kit"."""
        self.assertEqual(BrandKit.objects.count(), 0)

        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)

        kit = response.json()["brandKit"]
        self.assertEqual(kit["instituteName"], "")
        self.assertEqual(kit["logos"], [])
        self.assertEqual(BrandKit.objects.count(), 1)

    def test_fields_update_independently(self):
        self.client.patch(
            self.URL, {"instituteName": "Central School"}, format="json"
        )
        response = self.client.patch(
            self.URL, {"accentColor": "#2f5fdd"}, format="json"
        )
        self.assertEqual(response.status_code, 200)

        kit = response.json()["brandKit"]
        self.assertEqual(kit["instituteName"], "Central School", "not clobbered")
        self.assertEqual(kit["accentColor"], "#2f5fdd")

    def test_a_field_can_be_cleared(self):
        """Removing an address means sending an empty string, so emptiness has
        to be distinguishable from absence."""
        self.client.patch(self.URL, {"instituteAddress": "12 Road"}, format="json")
        response = self.client.patch(
            self.URL, {"instituteAddress": ""}, format="json"
        )
        self.assertEqual(response.json()["brandKit"]["instituteAddress"], "")

    def test_a_nonsense_accent_colour_is_refused(self):
        response = self.client.patch(
            self.URL, {"accentColor": "not-a-colour"}, format="json"
        )
        self.assertEqual(response.status_code, 400)

    def test_hex_colours_of_every_accepted_length_are_allowed(self):
        for value in ("#fff", "#2f5fdd", "#2f5fddcc"):
            response = self.client.patch(
                self.URL, {"accentColor": value}, format="json"
            )
            self.assertEqual(response.status_code, 200, value)

    def test_an_empty_patch_is_rejected(self):
        self.assertEqual(self.client.patch(self.URL, {}, format="json").status_code, 400)

    def test_a_teacher_only_ever_sees_their_own_kit(self):
        other = User.objects.create(email="o@example.com", name="O", status="approved")
        BrandKit.objects.create(user=other, institute_name="Their School")

        kit = self.client.get(self.URL).json()["brandKit"]
        self.assertEqual(kit["instituteName"], "")


class BrandAssetApiTests(BrandKitTestCase):
    URL = "/api/auth/brand-kit/assets"

    def tearDown(self):
        # The uploads are real files under MEDIA_ROOT in tests; leaving them
        # behind would accumulate across runs.
        for asset in BrandAsset.objects.all():
            try:
                if asset.storage_path and default_storage.exists(asset.storage_path):
                    default_storage.delete(asset.storage_path)
            except Exception:
                pass

    def test_uploading_a_logo_records_its_size_and_a_stable_url(self):
        response = self.client.post(
            self.URL, {"file": an_upload(a_png(120, 40))}, format="multipart"
        )
        self.assertEqual(response.status_code, 201)

        asset = response.json()["asset"]
        self.assertEqual((asset["width"], asset["height"]), (120, 40))
        # Never a presigned link: a saved paper outlives any signature.
        self.assertNotIn("X-Amz-Signature", asset["url"])
        self.assertTrue(asset["url"])

    def test_an_uploaded_logo_shows_up_on_the_kit(self):
        self.client.post(
            self.URL, {"file": an_upload(a_png())}, format="multipart"
        )
        kit = self.client.get("/api/auth/brand-kit").json()["brandKit"]
        self.assertEqual(len(kit["logos"]), 1)

    def test_several_logos_are_supported(self):
        """A school crest and a board emblem sit side by side on a great many
        papers, which is why this is a table and not a column."""
        for name in ("crest.png", "board.png"):
            response = self.client.post(
                self.URL, {"file": an_upload(a_png(), name=name)}, format="multipart"
            )
            self.assertEqual(response.status_code, 201)
        self.assertEqual(BrandAsset.objects.count(), 2)

    def test_a_non_image_is_refused(self):
        response = self.client.post(
            self.URL,
            {"file": an_upload(b"%PDF-1.4", name="x.pdf", content_type="application/pdf")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(BrandAsset.objects.count(), 0)

    def test_svg_is_refused_even_though_it_is_an_image(self):
        """It is a script-bearing document, and it would be inlined into an
        exported page."""
        response = self.client.post(
            self.URL,
            {"file": an_upload(b"<svg/>", name="x.svg", content_type="image/svg+xml")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    def test_an_oversized_image_is_refused(self):
        from services.brand_kit import MAX_LOGO_BYTES

        huge = a_png() + b"\x00" * MAX_LOGO_BYTES
        response = self.client.post(
            self.URL, {"file": an_upload(huge)}, format="multipart"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(BrandAsset.objects.count(), 0)

    def test_uploading_nothing_is_refused(self):
        self.assertEqual(
            self.client.post(self.URL, {}, format="multipart").status_code, 400
        )

    def test_a_logo_can_be_renamed_and_deleted(self):
        created = self.client.post(
            self.URL, {"file": an_upload(a_png())}, format="multipart"
        ).json()["asset"]

        renamed = self.client.patch(
            f"{self.URL}/{created['id']}", {"name": "School crest"}, format="json"
        )
        self.assertEqual(renamed.json()["asset"]["name"], "School crest")

        deleted = self.client.delete(f"{self.URL}/{created['id']}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(BrandAsset.objects.count(), 0)

    def test_deleting_removes_the_stored_object_too(self):
        created = self.client.post(
            self.URL, {"file": an_upload(a_png())}, format="multipart"
        ).json()["asset"]
        path = BrandAsset.objects.get(id=created["id"]).storage_path
        self.assertTrue(default_storage.exists(path))

        self.client.delete(f"{self.URL}/{created['id']}")
        self.assertFalse(default_storage.exists(path))

    def test_another_teachers_logo_is_untouchable(self):
        other = User.objects.create(email="o@example.com", name="O", status="approved")
        their_kit = BrandKit.objects.create(user=other)
        theirs = BrandAsset.objects.create(
            kit=their_kit, storage_path="brand-assets/other/x.png", name="Theirs"
        )

        self.assertEqual(
            self.client.patch(
                f"{self.URL}/{theirs.id}", {"name": "Mine"}, format="json"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.delete(f"{self.URL}/{theirs.id}").status_code, 404
        )
        theirs.refresh_from_db()
        self.assertEqual(theirs.name, "Theirs")
