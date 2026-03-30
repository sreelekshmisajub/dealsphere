from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0007_rename_products_myntra__f32d11_idx_products_myntra__7758f4_idx"),
    ]

    operations = [
        migrations.AlterField(
            model_name="cartitem",
            name="selected_source",
            field=models.CharField(
                choices=[
                    ("local", "Local Store"),
                    ("amazon", "Amazon"),
                    ("flipkart", "Flipkart"),
                    ("myntra", "Myntra"),
                ],
                default="local",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="orderitem",
            name="source",
            field=models.CharField(
                choices=[
                    ("local", "Local Store"),
                    ("amazon", "Amazon"),
                    ("flipkart", "Flipkart"),
                    ("myntra", "Myntra"),
                ],
                default="local",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="pricehistory",
            name="source",
            field=models.CharField(
                choices=[
                    ("amazon", "Amazon"),
                    ("flipkart", "Flipkart"),
                    ("myntra", "Myntra"),
                    ("local", "Local Store"),
                ],
                max_length=20,
            ),
        ),
    ]
