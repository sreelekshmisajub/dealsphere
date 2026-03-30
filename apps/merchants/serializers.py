"""
Serializers for Merchants app
"""

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from django.utils import timezone
from apps.core.models import Merchant, Product, Offer, PriceMatchRequest, Category, Brand, Order
from apps.core.registration import create_merchant_account, validate_merchant_registration_data


class MerchantRegistrationSerializer(serializers.Serializer):
    """Merchant registration serializer"""
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=15)
    shop_name = serializers.CharField(max_length=200)
    business_category = serializers.CharField(max_length=100)
    address = serializers.CharField()
    location_lat = serializers.DecimalField(max_digits=10, decimal_places=8)
    location_lng = serializers.DecimalField(max_digits=11, decimal_places=8)
    delivery_enabled = serializers.BooleanField(required=False, default=False)
    delivery_radius_km = serializers.IntegerField(required=False, default=0)
    gstin = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        try:
            validate_merchant_registration_data(attrs)
        except Exception as exc:
            raise serializers.ValidationError(str(exc))
        return attrs

    def create(self, validated_data):
        return create_merchant_account(validated_data, activity_source="api")

class MerchantProfileSerializer(serializers.ModelSerializer):
    """Merchant profile serializer"""
    user_info = serializers.SerializerMethodField()
    total_products = serializers.SerializerMethodField()
    active_offers = serializers.SerializerMethodField()

    class Meta:
        model = Merchant
        ref_name = 'MerchantProfile'
        fields = ['id', 'shop_name', 'business_category', 'gstin', 'address', 'location_lat', 'location_lng',
                 'verified', 'rating', 'total_reviews', 'delivery_enabled', 'delivery_radius_km',
                 'user_info', 'total_products', 'active_offers', 'created_at', 'updated_at']
        read_only_fields = ['id', 'verified', 'rating', 'total_reviews', 'created_at', 'updated_at']

    @extend_schema_field(serializers.DictField())
    def get_user_info(self, obj):
        """Get user information"""
        user = obj.user
        return {
            'id': user.id,
            'email': user.email,
            'phone': user.phone,
            'first_name': user.first_name,
            'last_name': user.last_name
        }

    @extend_schema_field(serializers.IntegerField())
    def get_total_products(self, obj):
        """Get total products count"""
        return Product.objects.filter(offers__merchant=obj).distinct().count()

    @extend_schema_field(serializers.IntegerField())
    def get_active_offers(self, obj):
        """Get active offers count"""
        return Offer.objects.filter(merchant=obj, is_active=True).count()

class ProductSerializer(serializers.ModelSerializer):
    """Product serializer for merchants"""
    category_name = serializers.CharField(source='category.name', read_only=True)
    brand_name = serializers.CharField(source='brand.name', read_only=True)
    offers_count = serializers.SerializerMethodField()
    merchant_offer = serializers.SerializerMethodField()

    class Meta:
        model = Product
        ref_name = 'MerchantProduct'
        fields = ['id', 'name', 'barcode', 'category', 'brand', 'category_name', 'brand_name',
                 'description', 'image_url', 'amazon_url', 'flipkart_url',
                 'amazon_price', 'flipkart_price', 'offers_count', 'merchant_offer', 'created_at', 'updated_at']

    @extend_schema_field(serializers.IntegerField())
    def get_offers_count(self, obj):
        """Get offers count for this product"""
        return Offer.objects.filter(product=obj, merchant__isnull=False).count()

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_merchant_offer(self, obj):
        """Return the current merchant's offer when serializer context includes a merchant."""
        merchant = self.context.get("merchant")
        if not merchant:
            return None

        offer = obj.offers.filter(merchant=merchant).order_by("-updated_at").first()
        if not offer:
            return None

        return {
            "id": offer.id,
            "price": float(offer.price),
            "original_price": float(offer.original_price) if offer.original_price else None,
            "delivery_time_hours": offer.delivery_time_hours,
            "delivery_cost": float(offer.delivery_cost),
            "stock_quantity": offer.stock_quantity,
            "is_active": offer.is_active,
        }

    def validate_barcode(self, value):
        """Validate barcode uniqueness"""
        if value:
            queryset = Product.objects.filter(barcode=value)
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists() and not self.context.get("allow_existing_barcode"):
                raise serializers.ValidationError("Product with this barcode already exists")
        return value

class OfferSerializer(serializers.ModelSerializer):
    """Offer serializer for merchants"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_barcode = serializers.CharField(source='product.barcode', read_only=True)
    merchant_name = serializers.CharField(source='merchant.shop_name', read_only=True)
    discount_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Offer
        ref_name = 'MerchantOffer'
        fields = ['id', 'product', 'product_name', 'product_barcode', 'merchant', 'merchant_name',
                 'price', 'original_price', 'discount_percentage', 'delivery_time_hours',
                 'delivery_cost', 'stock_quantity', 'is_active', 'valid_until',
                 'created_at', 'updated_at']
        read_only_fields = ['id', 'merchant', 'created_at', 'updated_at']

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_discount_percentage(self, obj):
        """Calculate discount percentage"""
        if obj.original_price and obj.original_price > obj.price:
            discount = ((obj.original_price - obj.price) / obj.original_price) * 100
            return round(discount, 2)
        return None

    def validate_price(self, value):
        """Validate price"""
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than 0")
        return value

    def validate_original_price(self, value):
        """Validate original price"""
        if value and value <= 0:
            raise serializers.ValidationError("Original price must be greater than 0")
        return value

    def validate(self, attrs):
        """Validate offer data"""
        price = attrs.get('price')
        original_price = attrs.get('original_price')
        
        if original_price and price > original_price:
            raise serializers.ValidationError("Price cannot be greater than original price")
        
        if attrs.get('valid_until') and attrs.get('valid_until') <= timezone.now():
            raise serializers.ValidationError("Valid until date must be in the future")
        
        return attrs

class PriceMatchRequestSerializer(serializers.ModelSerializer):
    """Price match request serializer for merchants"""
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_barcode = serializers.CharField(source='product.barcode', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    user_phone = serializers.CharField(source='user.phone', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = PriceMatchRequest
        ref_name = 'MerchantPriceMatchRequest'
        fields = ['id', 'user', 'user_email', 'user_phone', 'merchant', 'product',
                 'product_name', 'product_barcode', 'requested_price', 'competitor_price',
                 'competitor_source', 'status', 'status_display', 'response_message',
                 'created_at', 'updated_at', 'expires_at']
        read_only_fields = ['id', 'user', 'merchant', 'product', 'created_at', 'updated_at', 'expires_at']

class PriceMatchResponseSerializer(serializers.ModelSerializer):
    """Price match response serializer"""
    
    class Meta:
        model = PriceMatchRequest
        fields = ['status', 'response_message']
    
    def validate_status(self, value):
        """Validate status"""
        valid_statuses = ['approved', 'rejected', 'expired']
        if value not in valid_statuses:
            raise serializers.ValidationError(f"Status must be one of {valid_statuses}")
        return value

class CategorySerializer(serializers.ModelSerializer):
    """Category serializer"""
    class Meta:
        model = Category
        ref_name = 'MerchantCategory'
        fields = ['id', 'name', 'parent', 'level', 'created_at']
        read_only_fields = ['id', 'level', 'created_at']

class BrandSerializer(serializers.ModelSerializer):
    """Brand serializer"""
    class Meta:
        model = Brand
        ref_name = 'MerchantBrand'
        fields = ['id', 'name', 'created_at']
        read_only_fields = ['id', 'created_at']


class MerchantOrderSerializer(serializers.ModelSerializer):
    """Merchant-facing order serializer"""
    user_email = serializers.CharField(source='user.email', read_only=True)
    merchant_items = serializers.SerializerMethodField()

    class Meta:
        model = Order
        ref_name = 'MerchantOrder'
        fields = [
            'id',
            'user_email',
            'total_amount',
            'status',
            'payment_method',
            'payment_status',
            'payment_reference',
            'delivery_address',
            'merchant_items',
            'created_at',
            'updated_at',
        ]

    @extend_schema_field(serializers.ListField())
    def get_merchant_items(self, obj):
        merchant = self.context.get('merchant')
        items = obj.items.filter(merchant=merchant).select_related('product')
        return [
            {
                'product_id': item.product_id,
                'product_name': item.product.name,
                'quantity': item.quantity,
                'price': float(item.price),
                'source': item.source,
                'source_name': item.source_name,
                'delivery_time_hours': item.delivery_time_hours,
            }
            for item in items
        ]


class MerchantDashboardSerializer(serializers.Serializer):
    """Serializer for merchant dashboard summary payloads."""
    merchant = MerchantProfileSerializer()
    analytics = serializers.DictField()
    recent_price_match_requests = PriceMatchRequestSerializer(many=True)
    recent_offers = OfferSerializer(many=True)


class MerchantBulkPriceUpdateSerializer(serializers.Serializer):
    """Bulk merchant price update payload."""
    offer_id = serializers.IntegerField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
