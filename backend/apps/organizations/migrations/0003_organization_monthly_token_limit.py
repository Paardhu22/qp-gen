from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("organizations", "0002_organization_address_line1_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="monthly_token_limit",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
