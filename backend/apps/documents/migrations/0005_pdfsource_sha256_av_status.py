# Generated migration for sha256 and av_status fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0004_restore_pdfsource_content_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='pdfsource',
            name='sha256',
            field=models.CharField(blank=True, db_index=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name='pdfsource',
            name='av_status',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
    ]
