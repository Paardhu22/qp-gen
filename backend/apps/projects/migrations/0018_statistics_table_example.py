"""Teach STATISTICS_COMPUTE to print a real table.

The type's example was a header-less, row-wise table, so the generator copied
that shape and the editor had no column headings to show. The example is now a
`Class interval | Frequency` table under a header row (and its sample answer is
corrected: that data gives a mean of 20.67, not 20.3).

Reads a frozen snapshot, as 0016 and 0017 do. Only this one type changed since
0017 — no family, rename or alias row did — so only it is upserted.
"""

import json
from pathlib import Path

from django.db import migrations

SNAPSHOT = Path(__file__).resolve().parent / "data" / "question_types_0018.json"
CHANGED = {"STATISTICS_COMPUTE"}


def seed_types(apps, schema_editor):
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    QuestionFamily = apps.get_model("projects", "QuestionFamily")
    QuestionType = apps.get_model("projects", "QuestionType")

    families = {family.code: family for family in QuestionFamily.objects.all()}
    for row in data["types"]:
        if row["code"] not in CHANGED:
            continue
        defaults = {key: value for key, value in row.items() if key not in {"code", "family"}}
        defaults["family"] = families[row["family"]]
        defaults["deprecated_at"] = None
        QuestionType.objects.update_or_create(code=row["code"], defaults=defaults)


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0017_ict_question_types"),
    ]

    operations = [
        migrations.RunPython(seed_types, migrations.RunPython.noop),
    ]
