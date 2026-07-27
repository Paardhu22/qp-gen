"""Every service and view module must import cleanly.

This exists because of a specific, expensive failure. When paper content moved
from ``Paper.content`` onto ``PaperSet.content``, three modules kept importing
the paper-level helpers that had been deleted:

    services/answer_script_service.py       -> answer-script generation, 500
    apps/projects/management/commands/...   -> the S3 backfill command
    apps/projects/tests.py                  -> the tests that covered all of it

None of it surfaced. ``manage.py check`` does not catch it because the views
import these modules *lazily*, inside the request handler — so the ImportError
only fires when a user clicks the button, where a broad ``except Exception``
turns it into a generic 500. And the one thing that would have caught it, the
test module, was itself broken in the same way, so Django reported it as a
loader error among the noise and the suite stayed red without anyone acting.

A lazy import is a reasonable thing to write (it keeps startup fast and avoids
import cycles), so the fix is not to ban them — it is to import everything
once, here, where breakage is loud and instant.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from django.test import SimpleTestCase

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

#: Packages whose every module must be importable.
WATCHED_PACKAGES = ("services", "apps")

#: Directories of throwaway scripts, not application code.
EXCLUDED_PREFIXES = ("scratch", "scripts")


def _module_names() -> list[str]:
    names: list[str] = []
    for package_name in WATCHED_PACKAGES:
        package = importlib.import_module(package_name)
        for info in pkgutil.walk_packages(
            package.__path__, prefix=f"{package_name}."
        ):
            short = info.name.split(".", 1)[1] if "." in info.name else ""
            if short.startswith(EXCLUDED_PREFIXES):
                continue
            # Migrations are exercised by the test DB build; importing them
            # here adds hundreds of modules for no extra coverage.
            if ".migrations." in info.name or info.name.endswith(".migrations"):
                continue
            names.append(info.name)
    return sorted(names)


class ModuleImportSmokeTests(SimpleTestCase):
    def test_every_service_and_app_module_imports(self):
        failures: list[str] = []
        for name in _module_names():
            try:
                importlib.import_module(name)
            except Exception as exc:  # noqa: BLE001 - the point is to catch all
                failures.append(f"{name}: {type(exc).__name__}: {exc}")

        self.assertEqual(
            failures,
            [],
            "These modules cannot be imported. A view that imports one lazily "
            "will 500 the moment a user reaches it:\n  "
            + "\n  ".join(failures),
        )

    def test_the_smoke_test_actually_covers_something(self):
        """Guard against the walker silently matching nothing — an empty
        sweep would pass forever while covering zero modules."""
        names = _module_names()
        self.assertGreater(len(names), 50, names[:10])
        self.assertIn("services.answer_script_service", names)
        self.assertIn("services.pool.pipeline", names)
        self.assertIn("apps.storage.views", names)
