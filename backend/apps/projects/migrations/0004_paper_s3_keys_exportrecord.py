from django.db import migrations, models
import django.db.models.deletion
import utils.ids


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
        ('projects', '0003_paper_answer_script_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='paper',
            name='s3_pdf_key',
            field=models.CharField(
                blank=True,
                db_column='s3PdfKey',
                max_length=1024,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='paper',
            name='s3_docx_key',
            field=models.CharField(
                blank=True,
                db_column='s3DocxKey',
                max_length=1024,
                null=True,
            ),
        ),
        migrations.CreateModel(
            name='ExportRecord',
            fields=[
                ('created_at', models.DateTimeField(auto_now_add=True, db_column='createdAt')),
                ('updated_at', models.DateTimeField(auto_now=True, db_column='updatedAt')),
                ('id', models.CharField(
                    default=utils.ids.generate_id,
                    editable=False,
                    max_length=32,
                    primary_key=True,
                    serialize=False,
                )),
                ('s3_key', models.CharField(db_column='s3Key', max_length=1024)),
                ('file_format', models.CharField(db_column='fileFormat', max_length=10)),
                ('user', models.ForeignKey(
                    db_column='userId',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='export_records',
                    to='accounts.user',
                )),
            ],
            options={
                'db_table': 'ExportRecord',
            },
        ),
    ]
