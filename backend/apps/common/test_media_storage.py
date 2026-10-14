"""Media storage: S3 must actually be the storage, and /media/ must not loop.

After the Django 5.2 upgrade, settings still named S3 through
DEFAULT_FILE_STORAGE, which Django 5.1 removed. Uploads went to the local disk
and every /media/ URL for an object in S3 redirected to itself.
"""

from __future__ import annotations

import importlib
import os
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from services.storage.media_urls import is_remote_storage

S3 = {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"}
LOCAL = {"BACKEND": "django.core.files.storage.FileSystemStorage"}
STATIC = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}


class StorageSettingsTests(SimpleTestCase):
    def _storage_settings_with_bucket(self, bucket: str):
        """(default backend, has DEFAULT_FILE_STORAGE) for settings.py with `bucket`."""
        import config.settings as module

        # settings.py loads .env with override=True, which would put the
        # developer's own bucket back over the one under test.
        with patch.dict(os.environ, {"AWS_STORAGE_BUCKET_NAME": bucket}), patch(
            "dotenv.load_dotenv"
        ):
            importlib.reload(module)
            # Read now: reload returns the same module object, so the restore
            # below would overwrite these values.
            result = (
                module.STORAGES["default"]["BACKEND"],
                hasattr(module, "DEFAULT_FILE_STORAGE"),
            )
        importlib.reload(module)  # restore what the rest of the suite saw
        return result

    def test_a_bucket_selects_s3_through_storages(self):
        backend, has_removed_setting = self._storage_settings_with_bucket("qp-gen-pdfs")
        self.assertEqual(backend, S3["BACKEND"])
        # The removed setting must not be the thing doing the work.
        self.assertFalse(has_removed_setting)

    def test_no_bucket_keeps_the_local_disk(self):
        backend, _ = self._storage_settings_with_bucket("")
        self.assertEqual(backend, LOCAL["BACKEND"])


class RemoteStorageDetectionTests(SimpleTestCase):
    @override_settings(STORAGES={"default": S3, "staticfiles": STATIC})
    def test_s3_backend_is_remote(self):
        self.assertTrue(is_remote_storage())

    @override_settings(
        STORAGES={"default": LOCAL, "staticfiles": STATIC},
        AWS_STORAGE_BUCKET_NAME="qp-gen-pdfs",
    )
    def test_a_bucket_name_alone_is_not_remote(self):
        # Exactly the post-upgrade state: a bucket set, the disk in use.
        self.assertFalse(is_remote_storage())


class ServeMediaTests(SimpleTestCase):
    @patch("apps.common.views.is_remote_storage", return_value=True)
    @patch(
        "apps.common.views.fresh_signed_media_url",
        return_value="https://bucket.s3.amazonaws.com/brand-assets/a.png?X-Amz-Signature=x",
    )
    def test_remote_storage_redirects_to_the_signed_url(self, _signed, _remote):
        response = self.client.get("/media/brand-assets/a.png")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("https://bucket.s3.amazonaws.com/"))

    @patch("apps.common.views.is_remote_storage", return_value=True)
    @patch("apps.common.views.fresh_signed_media_url", return_value="/media/brand-assets/a.png")
    def test_a_signed_url_that_is_this_path_does_not_redirect_to_itself(self, _signed, _remote):
        response = self.client.get("/media/brand-assets/a.png")
        # Served (here: not found on disk) rather than a 302 loop.
        self.assertNotEqual(response.status_code, 302)
