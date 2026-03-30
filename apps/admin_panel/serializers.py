"""
Serializers for Admin Panel app
"""

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from django.contrib.auth import get_user_model
from django.db.models import F, Sum
from apps.core.models import Merchant, Order, Product, Offer, PriceMatchRequest, Category, Brand, UserActivity

User = get_user_model()

class AdminUserSerializer(serializers.ModelSerializer):
    """Admin user serializer"""
    merchant_profile = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()
    last_login = serializers.DateTimeField(read_only=True)
    date_joined = serializers.DateTimeField(read_only=True)

    class Meta:
        model = User
        ref_name = 'AdminUser'
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'full_name',
                 'phone', 'is_merchant', 'is_verified', 'is_active', 'is_staff',
                 'merchant_profile', 'last_login', 'date_joined']
        read_only_fields = ['id', 'username', 'date_joined', 'last_login']

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_merchant_profile(self, obj):
        """Get merchant profile if exists"""
        try:
            merchant = obj.merchant_profile
            return {
                'id': merchant.id,
                'shop_name': merchant.shop_name,
                'verified': merchant.verified,
                'rating': float(merchant.rating),
                'created_at': merchant.created_at
            }
        except Merchant.DoesNotExist:
            return None

    @extend_schema_field(serializers.CharField())
    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()

class AdminMerchantSerializer(serializers.ModelSerializer):
    """Admin merchant serializer"""
    user_info = serializers.SerializerMethodField()
    total_products = serializers.SerializerMethodField()
    active_offers = serializers.SerializerMethodField()
    total_sales = serializers.SerializerMethodField()

    class Meta:
        model = Merchant
        ref_name = 'AdminMerchant'
        fields = ['id', 'shop_name', 'business_category', 'gstin', 'address', 'location_lat', 'location_lng',
                 'verified', 'rating', 'total_reviews', 'delivery_enabled', 'delivery_radius_km',
                 'user_info', 'total_products', 'active_offers', 'total_sales',
                 'created_at', 'updated_at']
        read_only_fields = ['id', 'rating', 'total_reviews', 'created_at', 'updated_at']

    @extend_schema_field(serializers.DictField())
    def get_user_info(self, obj):
        """Get user information"""
        return {
            'id': obj.user.id,
            'username': obj.user.username,
            'email': obj.user.email,
            'phone': obj.user.phone,
            'is_active': obj.user.is_active
        }

    @extend_schema_field(serializers.IntegerField())
    def get_total_products(self, obj):
        """Get total products count"""
        return Product.objects.filter(offers__merchant=obj).distinct().count()

    @extend_schema_field(serializers.IntegerField())
    def get_active_offers(self, obj):
        """Get active offers count"""
        return Offer.objects.filter(merchant=obj, is_active=True).count()

    @extend_schema_field(serializers.FloatField())
    def get_total_sales(self, obj):
        """Get total sales amount"""
        total = obj.orderitem_set.aggregate(total=Sum(F('price') * F('quantity')))['total']
        return float(total or 0)

class AdminProductSerializer(serializers.ModelSerializer):
    """Admin product serializer"""
    category_name = serializers.CharField(source='category.name', read_only=True)
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    offers_count = serializers.SerializerMethodField()
    lowest_price = serializers.SerializerMethodField()
    highest_price = serializers.SerializerMethodField()

    class Meta:
        model = Product
        ref_name = 'AdminProduct'
        fields = ['id', 'name', 'barcode', 'category', 'brand', 'category_name', 'brand_name',
                 'description', 'image_url', 'amazon_url', 'flipkart_url',
                 'amazon_price', 'flipkart_price', 'amazon_rating', 'flipkart_rating',
                 'offers_count', 'lowest_price', 'highest_price', 'created_at', 'updated_at']

    @extend_schema_field(serializers.IntegerField())
    def get_offers_count(self, obj):
        """Get offers count"""
        return Offer.objects.filter(product=obj).count()

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_lowest_price(self, obj):
        """Get lowest price"""
        lowest = Offer.objects.filter(product=obj, is_active=True).order_by('price').first()
        return float(lowest.price) if lowest else None

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_highest_price(self, obj):
        """Get highest price"""
        highest = Offer.objects.filter(product=obj, is_active=True).order_by('-price').first()
        return float(highest.price) if highest else None

class AdminOfferSerializer(serializers.ModelSerializer):
    """Admin offer serializer"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_barcode = serializers.CharField(source='product.barcode', read_only=True)
    merchant_name = serializers.CharField(source='merchant.shop_name', read_only=True)
    merchant_email = serializers.CharField(source='merchant.user.email', read_only=True)
    discount_percentage = serializers.SerializerMethodField()
    days_active = serializers.SerializerMethodField()

    class Meta:
        model = Offer
        ref_name = 'AdminOffer'
        fields = ['id', 'product', 'product_name', 'product_barcode', 'merchant', 'merchant_name',
                 'merchant_email', 'price', 'original_price', 'discount_percentage',
                 'delivery_time_hours', 'delivery_cost', 'stock_quantity', 'is_active',
                 'valid_until', 'days_active', 'created_at', 'updated_at']

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_discount_percentage(self, obj):
        """Calculate discount percentage"""
        if obj.original_price and obj.original_price > obj.price:
            discount = ((obj.original_price - obj.price) / obj.original_price) * 100
            return round(discount, 2)
        return None

    @extend_schema_field(serializers.IntegerField())
    def get_days_active(self, obj):
        """Get days since offer was created"""
        from django.utils import timezone
        days = (timezone.now() - obj.created_at).days
        return days

class AdminPriceMatchSerializer(serializers.ModelSerializer):
    """Admin price match serializer"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_barcode = serializers.CharField(source='product.barcode', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_phone = serializers.CharField(source='user.phone', read_only=True)
    merchant_name = serializers.CharField(source='merchant.shop_name', read_only=True)
    merchant_email = serializers.CharField(source='merchant.user.email', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    days_pending = serializers.SerializerMethodField()

    class Meta:
        model = PriceMatchRequest
        ref_name = 'AdminPriceMatch'
        fields = ['id', 'user', 'user_email', 'user_phone', 'merchant', 'merchant_name',
                 'merchant_email', 'product', 'product_name', 'product_barcode',
                 'requested_price', 'competitor_price', 'competitor_source',
                 'status', 'status_display', 'response_message', 'days_pending',
                 'created_at', 'updated_at', 'expires_at']

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_days_pending(self, obj):
        """Get days request has been pending"""
        if obj.status == 'pending':
            from django.utils import timezone
            days = (timezone.now() - obj.created_at).days
            return days
        return None

class AdminDashboardSerializer(serializers.Serializer):
    """Admin dashboard serializer"""
    overview = serializers.DictField()
    user_stats = serializers.DictField()
    merchant_stats = serializers.DictField()
    product_stats = serializers.DictField()
    offer_stats = serializers.DictField()
    price_match_stats = serializers.DictField()
    recent_activities = serializers.ListField()
    system_health = serializers.DictField()

class CategorySerializer(serializers.ModelSerializer):
    """Category serializer"""
    product_count = serializers.SerializerMethodField()
    parent_name = serializers.CharField(source='parent.name', read_only=True)

    class Meta:
        model = Category
        ref_name = 'AdminCategory'
        fields = ['id', 'name', 'parent', 'parent_name', 'level', 'product_count', 'created_at']
        read_only_fields = ['id', 'level', 'created_at']

    @extend_schema_field(serializers.IntegerField())
    def get_product_count(self, obj):
        """Get product count for category"""
        return Product.objects.filter(category=obj).count()

class BrandSerializer(serializers.ModelSerializer):
    """Brand serializer"""
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Brand
        ref_name = 'AdminBrand'
        fields = ['id', 'name', 'product_count', 'created_at']
        read_only_fields = ['id', 'created_at']

    @extend_schema_field(serializers.IntegerField())
    def get_product_count(self, obj):
        """Get product count for brand"""
        return Product.objects.filter(brand=obj).count()

class AdminActivitySerializer(serializers.ModelSerializer):
    """Admin activity serializer"""
    user_email = serializers.CharField(source='user.email', read_only=True)
    product_name = serializers.CharField(source='product.name', read_only=True)
    merchant_name = serializers.CharField(source='merchant.shop_name', read_only=True)

    class Meta:
        model = UserActivity
        ref_name = 'AdminActivity'
        fields = ['id', 'user', 'user_email', 'activity_type', 'product', 'product_name',
                 'merchant', 'merchant_name', 'metadata', 'created_at']
        read_only_fields = ['id', 'created_at']


class AdminOrderSerializer(serializers.ModelSerializer):
    """Admin order serializer"""
    user_email = serializers.CharField(source='user.email', read_only=True)
    items_summary = serializers.SerializerMethodField()

    class Meta:
        model = Order
        ref_name = 'AdminOrder'
        fields = [
            'id',
            'user',
            'user_email',
            'total_amount',
            'delivery_cost',
            'status',
            'payment_method',
            'payment_status',
            'payment_reference',
            'delivery_address',
            'items_summary',
            'created_at',
            'updated_at',
        ]

    @extend_schema_field(serializers.ListField())
    def get_items_summary(self, obj):
        return [
            {
                'product_name': item.product.name,
                'merchant_name': item.merchant.shop_name if item.merchant else None,
                'source': item.source,
                'source_name': item.source_name,
                'quantity': item.quantity,
                'price': float(item.price),
            }
            for item in obj.items.select_related('product', 'merchant').all()
        ]


class AdminBulkUserActionSerializer(serializers.Serializer):
    """Bulk admin action payload for users."""
    action = serializers.ChoiceField(choices=['activate', 'deactivate', 'verify', 'unverify'])
    user_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)


class AdminBulkMerchantVerificationSerializer(serializers.Serializer):
    """Bulk admin verification payload for merchants."""
    verified = serializers.BooleanField()
    merchant_ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)


class AdminStatusPayloadSerializer(serializers.Serializer):
    """Generic admin analytics/status payload."""
    payload = serializers.DictField()
