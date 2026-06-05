"""Restore PdfSource.content_type defensively.

Production databases were originally provisioned by Prisma with a
`content_type VARCHAR NOT NULL` column on the `pdf_source` table. Migration
0003 attempts to drop the column, but on existing production databases the
column survives (either because 0003 was not yet applied or because the
prior column was added with NOT NULL and no default).

This migration is idempotent:

* If the column does not exist, it is recreated with a NOT NULL default
  so Django inserts succeed.
* If the column already exists (NOT NULL, no default), a default is
  attached so any INSERT that omits the column falls back gracefully.

The corresponding Django model field is added via state_operations so
``PdfSource.objects.create(content_type=...)`` is valid Python.
"""

from django.db import migrations, models


def _ensure_content_type_column(apps, schema_editor):
    connection = schema_editor.connection
    introspection = connection.introspection
    with connection.cursor() as cursor:
        try:
            columns = {
                col.name for col in introspection.get_table_description(cursor, "pdf_source")
            }
        except Exception:
            columns = set()

        if connection.vendor == "postgresql":
            if "content_type" not in columns:
                cursor.execute(
                    'ALTER TABLE "pdf_source" '
                    'ADD COLUMN "content_type" VARCHAR(255) NOT NULL '
                    "DEFAULT 'application/pdf';"
                )
            else:
                cursor.execute(
                    'ALTER TABLE "pdf_source" '
                    'ALTER COLUMN "content_type" SET DEFAULT \'application/pdf\';'
                )
        else:
            # SQLite / other backends: only add the column if it is missing.
            # SQLite has limited ALTER COLUMN support, but ADD COLUMN works
            # fine and Django state will pass the value explicitly going forward.
            if "content_type" not in columns:
                cursor.execute(
                    'ALTER TABLE "pdf_source" '
                    'ADD COLUMN "content_type" VARCHAR(255) NOT NULL '
                    "DEFAULT 'application/pdf';"
                )


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0003_remove_pdfsource_file_fields"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="pdfsource",
                    name="content_type",
                    field=models.CharField(
                        blank=True,
                        default="application/pdf",
                        max_length=255,
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    _ensure_content_type_column,
                    reverse_code=migrations.RunPython.noop,
                ),
            ],
        ),
    ]
