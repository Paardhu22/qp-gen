import os
from types import SimpleNamespace
from unittest.mock import patch

import django
from django.apps import apps
from django.test import SimpleTestCase

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
if not apps.ready:
    django.setup()

import config.settings as project_settings
from services.llm.openai_client import _record_usage


class CommonTests(SimpleTestCase):
    def test_health_placeholder(self):
        self.assertTrue(True)


class SettingsEnvTests(SimpleTestCase):
    def test_int_env_clamps_invalid_and_out_of_range_values(self):
        with patch.dict("os.environ", {"QP_TEST_INT": "not-an-int"}):
            self.assertEqual(project_settings._int_env("QP_TEST_INT", 8, minimum=1), 8)

        with patch.dict("os.environ", {"QP_TEST_INT": "0"}):
            self.assertEqual(project_settings._int_env("QP_TEST_INT", 8, minimum=1), 1)

        with patch.dict("os.environ", {"QP_TEST_INT": "99"}):
            self.assertEqual(
                project_settings._int_env("QP_TEST_INT", 8, minimum=1, maximum=32),
                32,
            )


class CacheConfigTests(SimpleTestCase):
    """P3 statelessness pass: CACHES is env-driven — Redis when REDIS_URL is
    set (multi-instance shared cache), LocMem otherwise, and a graceful
    LocMem fallback when the redis package is missing."""

    def test_no_redis_url_selects_locmem(self):
        config = project_settings.build_cache_config("")
        self.assertEqual(
            config["default"]["BACKEND"],
            "django.core.cache.backends.locmem.LocMemCache",
        )

    def test_redis_url_selects_redis_backend(self):
        config = project_settings.build_cache_config(
            "redis://elasticache.example:6379/0", redis_importable=True
        )
        self.assertEqual(
            config["default"]["BACKEND"],
            "django.core.cache.backends.redis.RedisCache",
        )
        self.assertEqual(
            config["default"]["LOCATION"], "redis://elasticache.example:6379/0"
        )

    def test_missing_redis_package_falls_back_to_locmem(self):
        with self.assertLogs("config.settings", level="WARNING"):
            config = project_settings.build_cache_config(
                "redis://elasticache.example:6379/0", redis_importable=False
            )
        self.assertEqual(
            config["default"]["BACKEND"],
            "django.core.cache.backends.locmem.LocMemCache",
        )


class OpenAIUsageLoggingTests(SimpleTestCase):
    def test_record_usage_is_best_effort(self):
        usage = SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=2,
            total_tokens=12,
        )

        with patch(
            "services.llm.openai_client.ApiUsage.objects.create",
            side_effect=RuntimeError("db unavailable"),
        ):
            with self.assertLogs("[OPENAI_SERVICE]", level="WARNING") as logs:
                _record_usage(None, "image_caption", "gpt-4o", usage)

        self.assertIn("Failed to record image_caption usage", logs.output[0])


class AllowedOriginsTests(SimpleTestCase):
    """CORS matches the Origin header literally, so origin parsing is the
    difference between a working apex+www deployment and one that fails every
    cross-origin request from whichever host FRONTEND_URL does not name."""

    def test_single_origin(self):
        self.assertEqual(
            project_settings._origins("https://hsatedu.in", ""),
            ["https://hsatedu.in"],
        )

    def test_extra_origins_are_split_and_appended(self):
        self.assertEqual(
            project_settings._origins(
                "https://hsatedu.in",
                "https://www.hsatedu.in,https://staging.hsatedu.in",
            ),
            [
                "https://hsatedu.in",
                "https://www.hsatedu.in",
                "https://staging.hsatedu.in",
            ],
        )

    def test_trailing_slashes_are_stripped(self):
        # An origin is scheme+host+port; a trailing slash matches nothing.
        self.assertEqual(
            project_settings._origins("https://hsatedu.in/", ""),
            ["https://hsatedu.in"],
        )

    def test_whitespace_and_duplicates_are_dropped(self):
        self.assertEqual(
            project_settings._origins(
                "https://hsatedu.in",
                " https://www.hsatedu.in , https://hsatedu.in ,, ",
            ),
            ["https://hsatedu.in", "https://www.hsatedu.in"],
        )

    def test_empty_input_yields_no_origins(self):
        self.assertEqual(project_settings._origins("", ""), [])


class TestEndpointRoutingTests(SimpleTestCase):
    """The science-engine runner spends real OpenAI budget on hard-coded
    inputs. It is a management command now (`run_engine_slice`) and must not
    be reachable over HTTP under any setting."""

    def test_route_is_absent(self):
        from django.urls import NoReverseMatch, reverse

        with self.assertRaises(NoReverseMatch):
            reverse("test-science-engine")


class FakeStorage:
    """Just enough of a storage backend for serve_media: bytes by key."""

    def __init__(self, objects):
        self.objects = objects

    def size(self, path):
        if path not in self.objects:
            raise FileNotFoundError(path)
        return len(self.objects[path])

    def open(self, path, mode="rb"):
        import io

        return io.BytesIO(self.objects[path])


class ServeMediaInlineTests(SimpleTestCase):
    """`/media/<path>?inline=1` returns an image's bytes instead of redirecting.

    The exporters read an image's pixels in the browser, and a redirect to a
    presigned S3 URL is not CORS-clean (the browser asks S3 with Origin: null),
    so the logo and figures were silently left out of exported PDFs.
    """

    PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 64

    def _get(self, path, query="", remote=True, objects=None, **extra):
        from django.test import Client

        storage = FakeStorage(objects if objects is not None else {"brand/logo.png": self.PNG})
        with patch("apps.common.views.is_remote_storage", return_value=remote), patch(
            "apps.common.views.default_storage", storage
        ), patch(
            "apps.common.views.fresh_signed_media_url",
            return_value="https://bucket.s3.example/signed?sig=1",
        ):
            return Client().get(f"/media/{path}{query}", **extra)

    def test_inline_returns_the_bytes_not_a_redirect(self):
        response = self._get("brand/logo.png", "?inline=1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), self.PNG)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["Content-Length"], str(len(self.PNG)))
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("max-age", response["Cache-Control"])

    def test_the_frontend_origin_is_allowed_by_cors_on_the_streamed_bytes(self):
        origin = project_settings.CORS_ALLOWED_ORIGINS[0]
        response = self._get("brand/logo.png", "?inline=1", HTTP_ORIGIN=origin)
        self.assertEqual(response["Access-Control-Allow-Origin"], origin)

    def test_without_inline_it_still_redirects_to_a_signed_url(self):
        response = self._get("brand/logo.png")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://bucket.s3.example/signed?sig=1")

    def test_only_inline_equal_to_one_triggers_it(self):
        for query in ("?inline=0", "?inline=true", "?inline="):
            with self.subTest(query):
                self.assertEqual(self._get("brand/logo.png", query).status_code, 302)

    def test_other_file_types_are_never_streamed(self):
        objects = {"docs/paper.pdf": b"%PDF", "brand/logo.svg": b"<svg/>", "brand/readme": b"x"}
        for key in objects:
            with self.subTest(key):
                response = self._get(key, "?inline=1", objects=objects)
                self.assertEqual(response.status_code, 302)

    def test_every_raster_type_is_served_with_its_own_content_type(self):
        types = {"a.jpg": "image/jpeg", "a.JPEG": "image/jpeg", "a.webp": "image/webp", "a.gif": "image/gif"}
        for key, expected in types.items():
            with self.subTest(key):
                response = self._get(key, "?inline=1", objects={key: self.PNG})
                self.assertEqual(response["Content-Type"], expected)

    def test_an_oversize_image_is_refused_not_proxied(self):
        with patch("apps.common.views.INLINE_MAX_BYTES", 10):
            response = self._get("brand/logo.png", "?inline=1")
        self.assertEqual(response.status_code, 413)

    def test_a_missing_object_is_a_404_so_the_client_can_fall_back(self):
        self.assertEqual(self._get("brand/gone.png", "?inline=1", objects={}).status_code, 404)

    def test_path_traversal_is_still_refused(self):
        self.assertEqual(self._get("../secrets.png", "?inline=1").status_code, 404)

    def test_local_storage_is_unchanged(self):
        # Local storage already streams the bytes; `inline` changes nothing there.
        with patch("apps.common.views.static_serve") as serve:
            from django.http import HttpResponse

            serve.return_value = HttpResponse(b"local")
            response = self._get("brand/logo.png", "?inline=1", remote=False)
        self.assertEqual(response.content, b"local")
