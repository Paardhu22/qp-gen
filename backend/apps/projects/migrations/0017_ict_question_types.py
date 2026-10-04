"""Seed the ICT question types and TOOL_IDENTIFY's Class 9–10 range.

Adds SHORTCUT_KEY, SOFTWARE_STEPS and SPREADSHEET_FORMULA. Reads a frozen
snapshot, as 0016 does. Only types changed since 0016 — no family, rename or
alias row did — so only types are upserted.
"""

import json
from pathlib import Path

from django.db import migrations

SNAPSHOT = Path(__file__).resolve().parent / "data" / "question_types_0017.json"


def seed_types(apps, schema_editor):
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    QuestionFamily = apps.get_model("projects", "QuestionFamily")
    QuestionType = apps.get_model("projects", "QuestionType")

    families = {family.code: family for family in QuestionFamily.objects.all()}
    for row in data["types"]:
        defaults = {key: value for key, value in row.items() if key not in {"code", "family"}}
        defaults["family"] = families[row["family"]]
        defaults["deprecated_at"] = None
        QuestionType.objects.update_or_create(code=row["code"], defaults=defaults)


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0016_question_type_catalogue"),
    ]

    operations = [
        migrations.RunPython(seed_types, migrations.RunPython.noop),
    ]
