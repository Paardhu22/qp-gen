from django.db import migrations


def remove_file_fields(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("""
            ALTER TABLE "pdf_source"
                DROP COLUMN IF EXISTS "file",
                DROP COLUMN IF EXISTS "content_type";
            """)
    else:
        # SQLite: Drop columns one by one if supported, otherwise skip
        with connection.cursor() as cursor:
            introspection = connection.introspection
            columns = {col.name for col in introspection.get_table_description(cursor, "pdf_source")}
            for col in ["file", "content_type"]:
                if col in columns:
                    try:
                        cursor.execute(f'ALTER TABLE "pdf_source" DROP COLUMN "{col}";')
                    except Exception:
                        pass  # Ignore if SQLite version doesn't support DROP COLUMN


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0002_documentchunk_metadata"),
    ]

    operations = [
        migrations.RunPython(
            remove_file_fields,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
