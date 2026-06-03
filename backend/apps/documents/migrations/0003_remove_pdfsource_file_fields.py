from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0002_documentchunk_metadata"),
    ]

    operations = [
        migrations.RunSQL(
            sql='''
            ALTER TABLE "pdf_source"
                DROP COLUMN IF EXISTS "file",
                DROP COLUMN IF EXISTS "content_type";
            ''',
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
