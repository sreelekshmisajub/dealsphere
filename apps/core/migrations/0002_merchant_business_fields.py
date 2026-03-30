from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="merchant",
            name="business_category",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="merchant",
            name="delivery_enabled",
            field=models.BooleanField(default=False),
        ),
        migrations.AddIndex(
            model_name="merchant",
            index=models.Index(fields=["business_category"], name="merchants_busines_4158f4_idx"),
        ),
    ]
