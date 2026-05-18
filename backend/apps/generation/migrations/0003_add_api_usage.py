from django.db import migrations, models
import django.db.models.deletion
import utils.ids


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("generation", "0002_add_generation_timestamps"),
    ]

    operations = [
        migrations.CreateModel(
            name="ApiUsage",
            fields=[
                (
                    "id",
                    models.CharField(
                        primary_key=True,
                        max_length=32,
                        default=utils.ids.generate_id,
                        editable=False,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_column="createdAt")),
                ("updated_at", models.DateTimeField(auto_now=True, db_column="updatedAt")),
                ("operation", models.CharField(max_length=64)),
                ("model", models.CharField(blank=True, max_length=64)),
                ("prompt_tokens", models.IntegerField(default=0)),
                ("completion_tokens", models.IntegerField(default=0)),
                ("total_tokens", models.IntegerField(default=0)),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        db_column="userId",
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="api_usage",
                        to="accounts.user",
                    ),
                ),
            ],
            options={"db_table": "ApiUsage"},
        ),
    ]
