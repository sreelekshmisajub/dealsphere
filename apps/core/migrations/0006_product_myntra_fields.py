from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0005_rename_merchants_busines_4158f4_idx_merchants_busines_495e87_idx"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="myntra_price",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="myntra_rating",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=3, null=True),
        ),
        migrations.AddField(
            model_name="product",
            name="myntra_url",
            field=models.URLField(blank=True, max_length=500, null=True),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["myntra_price"], name="products_myntra__f32d11_idx"),
        ),
    ]
