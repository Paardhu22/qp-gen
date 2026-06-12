# Statelessness pass P2: dual-write mirror key for Paper.content.
# The content column itself is untouched and remains the source of truth.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0004_paper_s3_keys_exportrecord"),
    ]

    operations = [
        migrations.AddField(
            model_name="paper",
            name="s3_content_key",
            field=models.CharField(
                blank=True, db_column="s3ContentKey", max_length=1024, null=True
            ),
        ),
    ]
