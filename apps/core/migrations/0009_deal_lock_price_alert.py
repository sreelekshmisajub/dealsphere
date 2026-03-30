from django.db import migrations, models
import django.core.validators
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_add_myntra_source_choices"),
    ]

    operations = [
        migrations.CreateModel(
            name="DealLock",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="deal_locks",
                        to="core.user",
                    ),
                ),
                (
                    "offer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="locks",
                        to="core.offer",
                    ),
                ),
                ("locked_price", models.DecimalField(max_digits=10, decimal_places=2)),
                ("lock_duration_hours", models.PositiveIntegerField(default=24)),
                ("locked_until", models.DateTimeField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("expired", "Expired"),
                            ("used", "Used"),
                            ("cancelled", "Cancelled"),
                        ],
                        default="active",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "deal_locks",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="deallock",
            index=models.Index(fields=["user", "status"], name="deal_locks_user_status_idx"),
        ),
        migrations.AddIndex(
            model_name="deallock",
            index=models.Index(fields=["offer", "status"], name="deal_locks_offer_status_idx"),
        ),
        migrations.AddIndex(
            model_name="deallock",
            index=models.Index(fields=["locked_until"], name="deal_locks_locked_until_idx"),
        ),
        migrations.CreateModel(
            name="PriceAlert",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="price_alerts",
                        to="core.user",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="price_alerts",
                        to="core.product",
                    ),
                ),
                (
                    "target_price",
                    models.DecimalField(
                        max_digits=10,
                        decimal_places=2,
                        validators=[django.core.validators.MinValueValidator(Decimal("0.01"))],
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("last_notified_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "price_alerts",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AlterUniqueTogether(
            name="pricealert",
            unique_together={("user", "product")},
        ),
        migrations.AddIndex(
            model_name="pricealert",
            index=models.Index(fields=["product", "is_active"], name="price_alerts_product_active_idx"),
        ),
        migrations.AddIndex(
            model_name="pricealert",
            index=models.Index(fields=["user", "is_active"], name="price_alerts_user_active_idx"),
        ),
    ]
