from django.db.backends.signals import connection_created
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(connection_created)
def configure_sqlite(sender, connection, **kwargs):
    if connection.vendor == 'sqlite':
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA journal_mode=WAL;')
            cursor.execute('PRAGMA synchronous=NORMAL;')


@receiver(post_save, sender='core.PriceHistory')
def on_price_history_saved(sender, instance, created, **kwargs):
    """When a new price history entry is created, check price alerts."""
    if not created:
        return
    try:
        from apps.core.notification_service import NotificationService
        NotificationService.check_and_notify_price_alerts(
            product=instance.product,
            new_price=instance.price,
            source=instance.get_source_display(),
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error in price history signal: {e}")


@receiver(post_save, sender='core.Order')
def on_order_status_changed(sender, instance, created, **kwargs):
    """When order status changes, notify user."""
    if created:
        return  # Only notify on updates
    if instance.status in ('confirmed', 'processing', 'shipped', 'delivered', 'cancelled'):
        try:
            from apps.core.notification_service import NotificationService
            NotificationService.notify_order_update(instance.user, instance)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error in order signal: {e}")


@receiver(post_save, sender='core.PriceMatchRequest')
def on_price_match_status_changed(sender, instance, created, **kwargs):
    """When price match status changes to approved/rejected/expired, notify user."""
    if created:
        return
    if instance.status in ('approved', 'rejected', 'expired'):
        try:
            from apps.core.notification_service import NotificationService
            NotificationService.notify_price_match_update(instance.user, instance)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error in price match signal: {e}")
