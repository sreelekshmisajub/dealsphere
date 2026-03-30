from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_merchant_business_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="cartitem",
            name="delivery_time_hours",
            field=models.PositiveIntegerField(default=24),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="merchant",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="core.merchant"),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="selected_source",
            field=models.CharField(
                choices=[("local", "Local Store"), ("amazon", "Amazon"), ("flipkart", "Flipkart")],
                default="local",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="selected_source_name",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="cartitem",
            name="unit_price_snapshot",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name="order",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("cash_on_delivery", "Cash on Delivery"),
                    ("pay_in_store", "Pay in Store"),
                    ("external_redirect", "External Redirect"),
                ],
                default="cash_on_delivery",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="payment_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("paid", "Paid"),
                    ("redirect_required", "Redirect Required"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="external_url",
            field=models.URLField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="source",
            field=models.CharField(
                choices=[("local", "Local Store"), ("amazon", "Amazon"), ("flipkart", "Flipkart")],
                default="local",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="orderitem",
            name="source_name",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name="orderitem",
            name="merchant",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="core.merchant"),
        ),
    ]
