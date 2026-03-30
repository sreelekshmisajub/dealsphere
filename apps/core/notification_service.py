"""
Centralized notification service for DealSphere.
Creates Notification records and triggers alert logic.
"""
import logging
from django.utils import timezone
from django.db import models
from decimal import Decimal

logger = logging.getLogger(__name__)


class NotificationService:

    @staticmethod
    def notify_price_drop(user, product, old_price, new_price, source):
        """Send price drop notification to a user"""
        from apps.core.models import Notification
        savings = float(old_price) - float(new_price)
        pct = (savings / float(old_price)) * 100 if old_price else 0
        Notification.objects.create(
            user=user,
            title=f"Price Drop: {product.name[:50]}",
            message=f"Price dropped by \u20b9{savings:.0f} ({pct:.0f}%) on {source}. Now \u20b9{float(new_price):.0f}.",
            notification_type='price_drop',
        )

    @staticmethod
    def notify_offer_available(user, product, merchant):
        """Notify user about new offer"""
        from apps.core.models import Notification
        Notification.objects.create(
            user=user,
            title=f"New Offer: {product.name[:50]}",
            message=f"{merchant.shop_name} has a new offer on {product.name}.",
            notification_type='offer_available',
        )

    @staticmethod
    def notify_price_match_update(user, price_match_request):
        """Notify user of price match status change"""
        from apps.core.models import Notification
        status_msg = {
            'approved': f"Your price match request was approved! New price: \u20b9{float(price_match_request.requested_price):.0f}",
            'rejected': f"Your price match request was rejected. {price_match_request.response_message or ''}",
            'expired': "Your price match request has expired.",
        }.get(price_match_request.status, f"Price match request updated to {price_match_request.status}.")
        Notification.objects.create(
            user=user,
            title=f"Price Match {price_match_request.status.title()}: {price_match_request.product.name[:40]}",
            message=status_msg,
            notification_type='price_match',
        )

    @staticmethod
    def notify_order_update(user, order):
        """Notify user of order status change"""
        from apps.core.models import Notification
        status_labels = {
            'confirmed': 'Your order has been confirmed.',
            'processing': 'Your order is being processed.',
            'shipped': 'Your order has been shipped.',
            'delivered': 'Your order has been delivered.',
            'cancelled': 'Your order has been cancelled.',
        }
        msg = status_labels.get(order.status, f"Order status updated to {order.status}.")
        Notification.objects.create(
            user=user,
            title=f"Order {order.status.title()}",
            message=msg,
            notification_type='order_update',
        )

    @staticmethod
    def notify_deal_lock(user, deal_lock):
        """Notify user that a deal has been locked"""
        from apps.core.models import Notification
        Notification.objects.create(
            user=user,
            title=f"Deal Locked: {deal_lock.offer.product.name[:50]}",
            message=(
                f"You have locked the price of \u20b9{float(deal_lock.locked_price):.0f} "
                f"for {deal_lock.offer.product.name[:40]} until "
                f"{deal_lock.locked_until.strftime('%d %b %Y, %I:%M %p')}."
            ),
            notification_type='offer_available',
        )

    @staticmethod
    def notify_deal_lock_expiring(user, deal_lock):
        """Notify user their deal lock is expiring"""
        from apps.core.models import Notification
        Notification.objects.create(
            user=user,
            title="Deal Lock Expiring Soon",
            message=(
                f"Your locked price of \u20b9{float(deal_lock.locked_price):.0f} "
                f"for {deal_lock.offer.product.name[:40]} expires at "
                f"{deal_lock.locked_until.strftime('%I:%M %p')}."
            ),
            notification_type='offer_available',
        )

    @staticmethod
    def check_and_notify_price_alerts(product, new_price, source):
        """
        Check all active PriceAlerts for this product.
        If new_price <= target_price, fire a notification.
        Rate-limit: only notify if last_notified_at is None or > 24h ago.
        """
        from apps.core.models import PriceAlert
        if not new_price:
            return
        new_price = Decimal(str(new_price))
        now = timezone.now()
        cutoff = now - timezone.timedelta(hours=24)

        alerts = PriceAlert.objects.filter(
            product=product,
            target_price__gte=new_price,
            is_active=True,
        ).filter(
            models.Q(last_notified_at__isnull=True) |
            models.Q(last_notified_at__lt=cutoff)
        ).select_related('user', 'product')

        for alert in alerts:
            try:
                NotificationService.notify_price_drop(
                    user=alert.user,
                    product=product,
                    old_price=alert.target_price,
                    new_price=new_price,
                    source=source,
                )
                alert.last_notified_at = now
                alert.save(update_fields=['last_notified_at'])
            except Exception as e:
                logger.error(f"Error sending price alert notification: {e}")
