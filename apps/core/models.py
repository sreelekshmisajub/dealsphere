"""
Core Django models for DealSphere
Optimized for real queries and performance
"""

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
import uuid

# Import custom managers
from .managers import (
    ProductManager, OfferManager, MerchantManager,
    PriceMatchRequestManager, NotificationManager,
    OrderManager, UserActivityManager, PriceHistoryManager
)

class User(AbstractUser):
    """Custom user model for DealSphere"""
    phone = models.CharField(max_length=15, blank=True, null=True)
    is_merchant = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    location_lat = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    location_lng = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['is_merchant']),
            models.Index(fields=['created_at']),
        ]

class Merchant(models.Model):
    """Merchant/Shop owner model"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='merchant_profile')
    shop_name = models.CharField(max_length=200)
    business_category = models.CharField(max_length=100, blank=True, null=True)
    gstin = models.CharField(max_length=15, blank=True, null=True)
    location_lat = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    location_lng = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    address = models.TextField(blank=True, null=True)
    verified = models.BooleanField(default=False)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.0)
    total_reviews = models.PositiveIntegerField(default=0)
    delivery_enabled = models.BooleanField(default=False)
    delivery_radius_km = models.PositiveIntegerField(default=10)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'merchants'
        indexes = [
            models.Index(fields=['shop_name']),
            models.Index(fields=['business_category']),
            models.Index(fields=['verified']),
            models.Index(fields=['rating']),
            models.Index(fields=['location_lat', 'location_lng']),
        ]

class Category(models.Model):
    """Product category model"""
    name = models.CharField(max_length=100, unique=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    level = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'categories'
        verbose_name_plural = 'categories'
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['parent']),
            models.Index(fields=['level']),
        ]

class Brand(models.Model):
    """Product brand model"""
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'brands'
        indexes = [
            models.Index(fields=['name']),
        ]

class Product(models.Model):
    """Product model"""
    name = models.CharField(max_length=300)
    barcode = models.CharField(max_length=50, unique=True, null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    description = models.TextField(blank=True, null=True)
    image_url = models.URLField(max_length=500, blank=True, null=True)
    amazon_url = models.URLField(max_length=500, blank=True, null=True)
    flipkart_url = models.URLField(max_length=500, blank=True, null=True)
    myntra_url = models.URLField(max_length=500, blank=True, null=True)
    amazon_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    flipkart_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    myntra_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    amazon_rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    flipkart_rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    myntra_rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Custom manager
    objects = models.Manager()
    products = ProductManager()

    class Meta:
        db_table = 'products'
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['barcode']),
            models.Index(fields=['category']),
            models.Index(fields=['brand']),
            models.Index(fields=['amazon_price']),
            models.Index(fields=['flipkart_price']),
            models.Index(fields=['myntra_price']),
            models.Index(fields=['created_at']),
        ]

class Offer(models.Model):
    """Product offer from merchant"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='offers')
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name='offers')
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    original_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    delivery_time_hours = models.PositiveIntegerField(help_text="Delivery time in hours")
    delivery_cost = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    stock_quantity = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Custom manager
    objects = models.Manager()
    offers = OfferManager()

    class Meta:
        db_table = 'offers'
        indexes = [
            models.Index(fields=['product', 'is_active']),
            models.Index(fields=['merchant', 'is_active']),
            models.Index(fields=['price']),
            models.Index(fields=['delivery_time_hours']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['price']

class Cart(models.Model):
    """User shopping cart"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='cart')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'carts'
        indexes = [
            models.Index(fields=['user']),
        ]

class CartItem(models.Model):
    """Cart item model"""
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    merchant = models.ForeignKey('Merchant', on_delete=models.SET_NULL, null=True, blank=True)
    selected_source = models.CharField(
        max_length=20,
        choices=[
            ('local', 'Local Store'),
            ('amazon', 'Amazon'),
            ('flipkart', 'Flipkart'),
            ('myntra', 'Myntra'),
        ],
        default='local'
    )
    selected_source_name = models.CharField(max_length=100, null=True, blank=True)
    unit_price_snapshot = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    delivery_time_hours = models.PositiveIntegerField(default=24)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cart_items'
        indexes = [
            models.Index(fields=['cart', 'product']),
            models.Index(fields=['added_at']),
        ]
        unique_together = ['cart', 'product']

class PriceMatchRequest(models.Model):
    """Price match request model"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='price_match_requests')
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, related_name='price_match_requests')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    requested_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    competitor_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    competitor_source = models.CharField(max_length=50, blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('expired', 'Expired'),
        ],
        default='pending'
    )
    response_message = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    # Custom manager
    objects = models.Manager()
    requests = PriceMatchRequestManager()

    class Meta:
        db_table = 'price_match_requests'
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['merchant', 'status']),
            models.Index(fields=['product', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['expires_at']),
        ]
        ordering = ['-created_at']

class Notification(models.Model):
    """User notification model"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=20,
        choices=[
            ('price_drop', 'Price Drop'),
            ('offer_available', 'Offer Available'),
            ('price_match', 'Price Match'),
            ('order_update', 'Order Update'),
            ('general', 'General'),
        ],
        default='general'
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    # Custom manager
    objects = models.Manager()
    notifications = NotificationManager()

    class Meta:
        db_table = 'notifications'
        indexes = [
            models.Index(fields=['user', 'is_read']),
            models.Index(fields=['notification_type']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['-created_at']

class Order(models.Model):
    """Order model"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    delivery_cost = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('0.00'))
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(
        max_length=30,
        choices=[
            ('cash_on_delivery', 'Cash on Delivery'),
            ('pay_in_store', 'Pay in Store'),
            ('upi', 'UPI'),
            ('online_gateway', 'Online Gateway'),
            ('external_redirect', 'External Redirect'),
        ],
        default='cash_on_delivery'
    )
    payment_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('paid', 'Paid'),
            ('redirect_required', 'Redirect Required'),
        ],
        default='pending'
    )
    payment_reference = models.CharField(max_length=120, blank=True, null=True)
    payment_link = models.CharField(max_length=1000, blank=True, null=True)
    delivery_address = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Custom manager
    objects = models.Manager()
    orders = OrderManager()

    class Meta:
        db_table = 'orders'
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['created_at']),
            models.Index(fields=['status']),
        ]
        ordering = ['-created_at']

class OrderItem(models.Model):
    """Order item model"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    merchant = models.ForeignKey(Merchant, on_delete=models.SET_NULL, null=True, blank=True)
    source = models.CharField(
        max_length=20,
        choices=[
            ('local', 'Local Store'),
            ('amazon', 'Amazon'),
            ('flipkart', 'Flipkart'),
            ('myntra', 'Myntra'),
        ],
        default='local'
    )
    source_name = models.CharField(max_length=100, null=True, blank=True)
    external_url = models.URLField(max_length=500, null=True, blank=True)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_time_hours = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'order_items'
        indexes = [
            models.Index(fields=['order', 'product']),
            models.Index(fields=['merchant']),
        ]

class UserActivity(models.Model):
    """User activity tracking"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=50)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True)
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Custom manager
    objects = models.Manager()
    activities = UserActivityManager()

    class Meta:
        db_table = 'user_activities'
        indexes = [
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['activity_type']),
            models.Index(fields=['product']),
        ]
        ordering = ['-created_at']

class PriceHistory(models.Model):
    """Price history tracking"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='price_history')
    source = models.CharField(max_length=20, choices=[
        ('amazon', 'Amazon'),
        ('flipkart', 'Flipkart'),
        ('myntra', 'Myntra'),
        ('local', 'Local Store'),
    ])
    price = models.DecimalField(max_digits=10, decimal_places=2)
    merchant = models.ForeignKey(Merchant, on_delete=models.CASCADE, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Custom manager
    objects = models.Manager()
    history = PriceHistoryManager()

    class Meta:
        db_table = 'price_history'
        indexes = [
            models.Index(fields=['product', 'source']),
            models.Index(fields=['created_at']),
            models.Index(fields=['price']),
        ]
        ordering = ['-created_at']


class DealLock(models.Model):
    """Lock an offer at current price for a limited time"""
    LOCK_STATUS = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('used', 'Used'),
        ('cancelled', 'Cancelled'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='deal_locks')
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='locks')
    locked_price = models.DecimalField(max_digits=10, decimal_places=2)
    lock_duration_hours = models.PositiveIntegerField(default=24)
    locked_until = models.DateTimeField()
    status = models.CharField(max_length=20, choices=LOCK_STATUS, default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'deal_locks'
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['offer', 'status']),
            models.Index(fields=['locked_until']),
        ]
        ordering = ['-created_at']


class PriceAlert(models.Model):
    """User price alert for a product"""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='price_alerts')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='price_alerts')
    target_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    is_active = models.BooleanField(default=True)
    last_notified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'price_alerts'
        unique_together = ['user', 'product']
        indexes = [
            models.Index(fields=['product', 'is_active']),
            models.Index(fields=['user', 'is_active']),
        ]
        ordering = ['-created_at']
