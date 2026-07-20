"""Database fields that behave correctly on both Postgres and SQLite.

Production runs Postgres; the test suite runs in-memory SQLite (see the
DATABASE_URL branch in config/settings.py). That split is fine until a model
uses `django.contrib.postgres.fields.ArrayField`, which has no SQLite
implementation at all — writing a non-empty array under SQLite fails with
`sqlite3.OperationalError: unrecognized token`.

`Question.options` has been an ArrayField since the Prisma-era schema, and the
gap went unnoticed only because no test ever wrote a non-empty option list.
The pool architecture auto-saves every generated MCQ, so the save path is now
central and must be testable.
"""

from __future__ import annotations

import json

from django.contrib.postgres.fields import ArrayField


class PortableArrayField(ArrayField):
    """ArrayField on Postgres, JSON-encoded TEXT everywhere else.

    Deliberately deconstructs as a plain `ArrayField` so Django's migration
    autodetector sees no change: the production column stays `text[]` and no
    ALTER runs against the live table. The only behavioural difference is on
    backends that cannot do arrays natively, where values round-trip as JSON.
    """

    def deconstruct(self):
        name, _path, args, kwargs = super().deconstruct()
        # Report the parent's path so this is migration-invisible.
        return name, "django.contrib.postgres.fields.ArrayField", args, kwargs

    def db_type(self, connection):
        if connection.vendor == "postgresql":
            return super().db_type(connection)
        return "text"

    def get_placeholder(self, value, compiler, connection):
        # ArrayField hardcodes a Postgres cast — "%s::text[]" — directly into
        # the SQL string. SQLite cannot parse "::" and fails with
        # "unrecognized token", which is the actual reason a non-empty option
        # list could never be written under test.
        if connection.vendor == "postgresql":
            return super().get_placeholder(value, compiler, connection)
        return "%s"

    def get_db_prep_value(self, value, connection, prepared=False):
        if connection.vendor == "postgresql":
            return super().get_db_prep_value(value, connection, prepared)
        if value is None:
            return None
        return json.dumps(list(value))

    def from_db_value(self, value, expression, connection):
        if connection.vendor == "postgresql":
            return value
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            return list(value)
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return []
        return decoded if isinstance(decoded, list) else []

    def to_python(self, value):
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
            except (TypeError, ValueError):
                return super().to_python(value)
            return decoded if isinstance(decoded, list) else []
        return super().to_python(value)
