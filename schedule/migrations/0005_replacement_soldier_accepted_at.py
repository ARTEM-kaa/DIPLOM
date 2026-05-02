# Generated manually — adds timestamp when replacement soldier agrees

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("schedule", "0004_unique_default_schedule_template"),
    ]

    operations = [
        migrations.AddField(
            model_name="replacementrequest",
            name="soldier_accepted_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Set when the requested replacement soldier agrees to swap.",
                null=True,
            ),
        ),
    ]
