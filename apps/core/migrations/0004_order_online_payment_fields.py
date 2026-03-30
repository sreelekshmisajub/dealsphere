from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_cartitem_source_tracking_order_payment"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="payment_link",
            field=models.CharField(blank=True, max_length=1000, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="payment_reference",
            field=models.CharField(blank=True, max_length=120, null=True),
        ),
        migrations.AlterField(
            model_name="order",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("cash_on_delivery", "Cash on Delivery"),
                    ("pay_in_store", "Pay in Store"),
                    ("upi", "UPI"),
                    ("online_gateway", "Online Gateway"),
                    ("external_redirect", "External Redirect"),
                ],
                default="cash_on_delivery",
                max_length=30,
            ),
        ),
    ]
