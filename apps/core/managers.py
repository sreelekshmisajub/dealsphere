"""
Custom model managers for DealSphere
"""

from django.db import models
from django.db.models import Q, Count, Avg, Min, Max
from django.utils import timezone
from datetime import timedelta

class ProductManager(models.Manager):
    """Custom manager for Product model"""
    
    def with_active_offers(self):
        """Get products with active offers"""
        return self.filter(
            offers__is_active=True,
            offers__valid_until__gt=timezone.now()
        ).distinct()
    
    def by_category(self, category_name):
        """Get products by category name"""
        return self.filter(category__name__icontains=category_name)
    
    def by_brand(self, brand_name):
        """Get products by brand name"""
        return self.filter(brand__name__icontains=brand_name)
    
    def search(self, query):
        """Search products by name or barcode"""
        return self.filter(
            Q(name__icontains=query) | Q(barcode__icontains=query)
        )
    
    def in_price_range(self, min_price=None, max_price=None):
        """Get products in price range"""
        queryset = self.all()
        if min_price is not None:
            queryset = queryset.filter(
                Q(amazon_price__gte=min_price) | Q(flipkart_price__gte=min_price) | Q(myntra_price__gte=min_price)
            )
        if max_price is not None:
            queryset = queryset.filter(
                Q(amazon_price__lte=max_price) | Q(flipkart_price__lte=max_price) | Q(myntra_price__lte=max_price)
            )
        return queryset.distinct()
    
    def with_price_drops(self, days=7):
        """Get products with recent price drops"""
        cutoff_date = timezone.now() - timedelta(days=days)
        return self.filter(
            price_history__created_at__gte=cutoff_date
        ).annotate(
            price_change=Count('price_history')
        ).filter(price_change__gt=1)

class OfferManager(models.Manager):
    """Custom manager for Offer model"""
    
    def active(self):
        """Get active offers"""
        return self.filter(
            is_active=True,
            valid_until__gt=timezone.now()
        )
    
    def by_merchant(self, merchant):
        """Get offers by merchant"""
        return self.filter(merchant=merchant)
    
    def by_product(self, product):
        """Get offers by product"""
        return self.filter(product=product)
    
    def cheapest_first(self, product=None):
        """Get cheapest offers first"""
        queryset = self.active()
        if product:
            queryset = queryset.filter(product=product)
        return queryset.order_by('price')
    
    def fastest_delivery(self, product=None):
        """Get offers with fastest delivery"""
        queryset = self.active()
        if product:
            queryset = queryset.filter(product=product)
        return queryset.order_by('delivery_time_hours')
    
    def in_radius(self, lat, lng, radius_km=10):
        """Get offers within radius (simplified)"""
        # In production, use proper geospatial queries
        return self.active().filter(
            merchant__location_lat__isnull=False,
            merchant__location_lng__isnull=False
        )

class MerchantManager(models.Manager):
    """Custom manager for Merchant model"""
    
    def verified(self):
        """Get verified merchants"""
        return self.filter(verified=True)
    
    def by_location(self, lat, lng, radius_km=10):
        """Get merchants by location (simplified)"""
        return self.filter(
            location_lat__isnull=False,
            location_lng__isnull=False
        )
    
    def top_rated(self, min_rating=4.0):
        """Get top rated merchants"""
        return self.filter(rating__gte=min_rating).order_by('-rating')
    
    def with_active_offers(self):
        """Get merchants with active offers"""
        return self.filter(
            offers__is_active=True,
            offers__valid_until__gt=timezone.now()
        ).distinct()
    
    def by_category(self, category):
        """Get merchants by product category"""
        return self.filter(
            offers__product__category=category,
            offers__is_active=True
        ).distinct()

class PriceMatchRequestManager(models.Manager):
    """Custom manager for PriceMatchRequest model"""
    
    def pending(self):
        """Get pending requests"""
        return self.filter(status='pending')
    
    def by_user(self, user):
        """Get requests by user"""
        return self.filter(user=user)
    
    def by_merchant(self, merchant):
        """Get requests by merchant"""
        return self.filter(merchant=merchant)
    
    def expired(self):
        """Get expired requests"""
        return self.filter(
            expires_at__lt=timezone.now(),
            status='pending'
        )
    
    def recent(self, days=7):
        """Get recent requests"""
        cutoff_date = timezone.now() - timedelta(days=days)
        return self.filter(created_at__gte=cutoff_date)
    
    def approve_rate(self):
        """Get approval rate"""
        total = self.count()
        if total == 0:
            return 0
        approved = self.filter(status='approved').count()
        return (approved / total) * 100

class NotificationManager(models.Manager):
    """Custom manager for Notification model"""
    
    def unread(self, user):
        """Get unread notifications for user"""
        return self.filter(user=user, is_read=False)
    
    def by_type(self, notification_type):
        """Get notifications by type"""
        return self.filter(notification_type=notification_type)
    
    def recent(self, days=7):
        """Get recent notifications"""
        cutoff_date = timezone.now() - timedelta(days=days)
        return self.filter(created_at__gte=cutoff_date)
    
    def price_drop_alerts(self, user):
        """Get price drop alerts for user"""
        return self.filter(
            user=user,
            notification_type='price_drop',
            is_read=False
        )

class OrderManager(models.Manager):
    """Custom manager for Order model"""
    
    def by_user(self, user):
        """Get orders by user"""
        return self.filter(user=user)
    
    def by_status(self, status):
        """Get orders by status"""
        return self.filter(status=status)
    
    def recent(self, days=30):
        """Get recent orders"""
        cutoff_date = timezone.now() - timedelta(days=days)
        return self.filter(created_at__gte=cutoff_date)
    
    def pending_processing(self):
        """Get orders pending processing"""
        return self.filter(status__in=['pending', 'confirmed'])
    
    def total_revenue(self, start_date=None, end_date=None):
        """Get total revenue in date range"""
        queryset = self.filter(status='delivered')
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        return queryset.aggregate(total=models.Sum('total_amount'))['total'] or 0

class UserActivityManager(models.Manager):
    """Custom manager for UserActivity model"""
    
    def by_user(self, user):
        """Get activities by user"""
        return self.filter(user=user)
    
    def by_type(self, activity_type):
        """Get activities by type"""
        return self.filter(activity_type=activity_type)
    
    def recent(self, days=7):
        """Get recent activities"""
        cutoff_date = timezone.now() - timedelta(days=days)
        return self.filter(created_at__gte=cutoff_date)
    
    def product_views(self, user):
        """Get product views by user"""
        return self.filter(user=user, activity_type='product_view')
    
    def search_activities(self, user):
        """Get search activities by user"""
        return self.filter(user=user, activity_type='search')

class PriceHistoryManager(models.Manager):
    """Custom manager for PriceHistory model"""
    
    def by_product(self, product):
        """Get price history by product"""
        return self.filter(product=product).order_by('-created_at')
    
    def by_source(self, source):
        """Get price history by source"""
        return self.filter(source=source)
    
    def recent(self, days=30):
        """Get recent price history"""
        cutoff_date = timezone.now() - timedelta(days=days)
        return self.filter(created_at__gte=cutoff_date)
    
    def price_changes(self, product, days=30):
        """Get price changes for product"""
        cutoff_date = timezone.now() - timedelta(days=days)
        return self.filter(
            product=product,
            created_at__gte=cutoff_date
        ).order_by('-created_at')
    
    def lowest_price(self, product):
        """Get lowest price for product"""
        return self.filter(product=product).aggregate(
            lowest=models.Min('price')
        )['lowest'] or 0
    
    def average_price(self, product, days=30):
        """Get average price for product"""
        cutoff_date = timezone.now() - timedelta(days=days)
        return self.filter(
            product=product,
            created_at__gte=cutoff_date
        ).aggregate(average=models.Avg('price'))['average'] or 0
