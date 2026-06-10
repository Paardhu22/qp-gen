from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0002_question_difficulty_question_grade_class_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='paper',
            name='answer_script_id',
            field=models.CharField(
                blank=True,
                db_column='answerScriptId',
                max_length=32,
                null=True,
            ),
        ),
    ]
