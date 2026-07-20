from django.db import migrations
from django.db.models import OuterRef, Subquery


def backfill_question_user(apps, schema_editor):
    """Populate Question.user from the owning Project.

    Questions were previously reachable only through project.user. The pool
    architecture queries the bank by owner directly, so every pre-existing row
    needs its userId set.

    Uses a correlated Subquery rather than raw SQL or a Python loop: raw
    ``UPDATE ... FROM`` is Postgres-only and would break the SQLite test
    database, while a row-by-row loop is O(n) round-trips against the live
    Neon/RDS instance.
    """
    Question = apps.get_model("projects", "Question")
    Project = apps.get_model("projects", "Project")

    Question.objects.filter(
        user__isnull=True, project__isnull=False
    ).update(
        user_id=Subquery(
            Project.objects.filter(id=OuterRef("project_id")).values("user_id")[:1]
        )
    )


def reverse_backfill(apps, schema_editor):
    """Clear the denormalised owner. project.user remains the source of truth,
    so this loses nothing."""
    Question = apps.get_model("projects", "Question")
    Question.objects.update(user=None)


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0006_question_content_hash_question_explanation_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_question_user, reverse_backfill),
    ]
