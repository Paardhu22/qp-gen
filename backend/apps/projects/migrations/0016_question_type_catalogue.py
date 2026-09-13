"""Seed the question type catalogue (services/question_types).

Reads a frozen snapshot rather than the live catalogue, so this migration does
the same thing whenever it runs. A later catalogue change needs a new migration
with its own snapshot (`manage.py export_question_types --snapshot …`).

What it does, in order:

1. Upserts the ten families (A–J).
2. Upserts every catalogue type, filling the descriptive columns 0012 left
   empty (`content_schema` carries the axes, `answer_schema` the marking).
3. Moves bank rows off the five renamed codes onto their new names, then
   deletes the old rows.
4. Adds alias rows: every runtime shape and every renamed code.
5. Deletes families nothing points at any more (`OBJECTIVE` split in two).
"""

import json
from pathlib import Path

from django.db import migrations

SNAPSHOT = Path(__file__).resolve().parent / "data" / "question_types_0016.json"


def seed_catalogue(apps, schema_editor):
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    QuestionFamily = apps.get_model("projects", "QuestionFamily")
    QuestionType = apps.get_model("projects", "QuestionType")
    QuestionTypeAlias = apps.get_model("projects", "QuestionTypeAlias")
    Question = apps.get_model("projects", "Question")

    for family in data["families"]:
        QuestionFamily.objects.update_or_create(
            code=family["code"],
            defaults={key: value for key, value in family.items() if key != "code"},
        )
    families = {family.code: family for family in QuestionFamily.objects.all()}

    for row in data["types"]:
        defaults = {key: value for key, value in row.items() if key not in {"code", "family"}}
        defaults["family"] = families[row["family"]]
        defaults["deprecated_at"] = None
        QuestionType.objects.update_or_create(code=row["code"], defaults=defaults)

    for old, new in data["renamed"].items():
        Question.objects.filter(type_id=old).update(type_id=new)
        QuestionType.objects.filter(code=old).delete()

    for alias in data["aliases"]:
        QuestionTypeAlias.objects.get_or_create(
            type_id=alias["type"],
            alias=alias["alias"],
            locale=None,
            board_code=None,
            defaults={"source": alias["source"]},
        )

    wanted = {family["code"] for family in data["families"]}
    QuestionFamily.objects.exclude(code__in=wanted).filter(types__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0015_draft_draft_unique_draft_per_scope_and_set"),
    ]

    operations = [
        migrations.RunPython(seed_catalogue, migrations.RunPython.noop),
    ]
