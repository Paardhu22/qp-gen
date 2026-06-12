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
from services.openai_service import _record_usage


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
            "services.openai_service.ApiUsage.objects.create",
            side_effect=RuntimeError("db unavailable"),
        ):
            with self.assertLogs("[OPENAI_SERVICE]", level="WARNING") as logs:
                _record_usage(None, "image_caption", "gpt-4o", usage)

        self.assertIn("Failed to record image_caption usage", logs.output[0])
