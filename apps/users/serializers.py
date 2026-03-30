"""
Serializers for Users app
"""

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from apps.core.models import User, Product, Cart, CartItem, Order, OrderItem
from apps.core.registration import create_customer_account, validate_customer_registration_data

class UserRegistrationSerializer(serializers.Serializer):
    """User registration serializer"""
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=15)
    location_lat = serializers.DecimalField(max_digits=10, decimal_places=8)
    location_lng = serializers.DecimalField(max_digits=11, decimal_places=8)
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        try:
            validate_customer_registration_data(attrs)
        except Exception as exc:
            raise serializers.ValidationError(str(exc))
        return attrs

    def create(self, validated_data):
        return create_customer_account(validated_data, activity_source="api")

class UserLoginSerializer(serializers.Serializer):
    """User login serializer"""
    email = serializers.EmailField()
    password = serializers.CharField()

class UserProfileSerializer(serializers.ModelSerializer):
    """User profile serializer"""
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        ref_name = 'UserProfile'
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'full_name', 
                 'phone', 'is_merchant', 'is_verified', 'location_lat', 'location_lng', 
                 'date_joined', 'last_login']
        read_only_fields = ['id', 'username', 'is_merchant', 'is_verified', 'date_joined', 'last_login']

    @extend_schema_field(serializers.CharField())
    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()

class ProductSearchSerializer(serializers.ModelSerializer):
    """Product search serializer"""
    best_offer = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    price_range = serializers.SerializerMethodField()

    class Meta:
        model = Product
        ref_name = 'UserProductSearch'
        fields = ['id', 'name', 'category', 'brand', 'barcode', 'image_url', 
                 'best_offer', 'rating', 'price_range', 'created_at']

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_best_offer(self, obj):
        """Get best offer for product"""
        best_offer = obj.offers.filter(is_active=True).order_by('price').first()
        if best_offer:
            return {
                'price': float(best_offer.price),
                'original_price': float(best_offer.original_price) if best_offer.original_price else None,
                'merchant': best_offer.merchant.shop_name,
                'delivery_time_hours': best_offer.delivery_time_hours,
                'delivery_cost': float(best_offer.delivery_cost),
                'discount_percentage': best_offer.discount_percentage,
                'source': 'local',
                'source_icon': 'fas fa-store'
            }

        online_sources = []
        if obj.amazon_price is not None:
            online_sources.append({
                'price': float(obj.amazon_price),
                'original_price': float(obj.amazon_price),
                'merchant': 'Amazon',
                'delivery_time_hours': 24,
                'delivery_cost': 0.0,
                'discount_percentage': None,
                'source': 'amazon',
                'source_icon': 'fab fa-amazon'
            })
        if obj.flipkart_price is not None:
            online_sources.append({
                'price': float(obj.flipkart_price),
                'original_price': float(obj.flipkart_price),
                'merchant': 'Flipkart',
                'delivery_time_hours': 48,
                'delivery_cost': 0.0,
                'discount_percentage': None,
                'source': 'flipkart',
                'source_icon': 'fas fa-bag-shopping'
            })
        if obj.myntra_price is not None:
            online_sources.append({
                'price': float(obj.myntra_price),
                'original_price': float(obj.myntra_price),
                'merchant': 'Myntra',
                'delivery_time_hours': 36,
                'delivery_cost': 0.0,
                'discount_percentage': None,
                'source': 'myntra',
                'source_icon': 'fas fa-shirt'
            })

        return min(online_sources, key=lambda item: item['price']) if online_sources else None

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_rating(self, obj):
        """Get best rating from sources"""
        ratings = []
        if obj.amazon_rating:
            ratings.append(obj.amazon_rating)
        if obj.flipkart_rating:
            ratings.append(obj.flipkart_rating)
        if obj.myntra_rating:
            ratings.append(obj.myntra_rating)
        return max(ratings) if ratings else None

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_price_range(self, obj):
        """Get price range from all sources"""
        prices = []
        if obj.amazon_price:
            prices.append(obj.amazon_price)
        if obj.flipkart_price:
            prices.append(obj.flipkart_price)
        if obj.myntra_price:
            prices.append(obj.myntra_price)
        
        # Add offer prices
        for offer in obj.offers.filter(is_active=True):
            prices.append(offer.price)
        
        if prices:
            return {
                'min': float(min(prices)),
                'max': float(max(prices))
            }
        return None

class CartSerializer(serializers.ModelSerializer):
    """Cart serializer"""
    items = serializers.SerializerMethodField()
    total_amount = serializers.SerializerMethodField()
    total_items = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        ref_name = 'UserCart'
        fields = ['id', 'user', 'items', 'total_amount', 'total_items', 'created_at', 'updated_at']
        read_only_fields = ['user', 'created_at', 'updated_at']

    @extend_schema_field(serializers.ListField(child=serializers.DictField()))
    def get_items(self, obj):
        """Get cart items with product details"""
        items = obj.items.select_related('product').all()
        return CartItemSerializer(items, many=True).data

    @extend_schema_field(serializers.DecimalField(max_digits=12, decimal_places=2))
    def get_total_amount(self, obj):
        """Calculate total amount"""
        total = 0
        for item in obj.items.all():
            price = item.unit_price_snapshot or 0
            total += price * item.quantity
        return total

    @extend_schema_field(serializers.IntegerField())
    def get_total_items(self, obj):
        """Get total item count"""
        return sum(item.quantity for item in obj.items.all())

class CartItemSerializer(serializers.ModelSerializer):
    """Cart item serializer"""
    product = ProductSearchSerializer(read_only=True)
    subtotal = serializers.SerializerMethodField()
    source = serializers.CharField(source='selected_source', read_only=True)
    source_name = serializers.CharField(source='selected_source_name', read_only=True)
    merchant_id = serializers.IntegerField(read_only=True)
    unit_price = serializers.DecimalField(source='unit_price_snapshot', max_digits=10, decimal_places=2, read_only=True)
    delivery_time_hours = serializers.IntegerField(read_only=True)

    class Meta:
        model = CartItem
        ref_name = 'UserCartItem'
        fields = [
            'id',
            'cart',
            'product',
            'merchant_id',
            'source',
            'source_name',
            'unit_price',
            'delivery_time_hours',
            'quantity',
            'subtotal',
            'added_at',
        ]
        read_only_fields = ['cart', 'added_at']

    @extend_schema_field(serializers.DecimalField(max_digits=12, decimal_places=2))
    def get_subtotal(self, obj):
        """Calculate subtotal for cart item"""
        price = obj.unit_price_snapshot or 0
        return price * obj.quantity


class OrderItemSerializer(serializers.ModelSerializer):
    """Order item serializer"""
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = OrderItem
        ref_name = 'UserOrderItem'
        fields = [
            'id',
            'product',
            'product_name',
            'merchant',
            'source',
            'source_name',
            'external_url',
            'quantity',
            'price',
            'delivery_time_hours',
            'created_at',
        ]


class OrderSerializer(serializers.ModelSerializer):
    """User order serializer"""
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        ref_name = 'UserOrder'
        fields = [
            'id',
            'total_amount',
            'delivery_cost',
            'status',
            'payment_method',
            'payment_status',
            'payment_reference',
            'payment_link',
            'delivery_address',
            'items',
            'created_at',
            'updated_at',
        ]


class LocationUpdateSerializer(serializers.Serializer):
    """User location update payload."""
    lat = serializers.DecimalField(max_digits=10, decimal_places=8)
    lng = serializers.DecimalField(max_digits=11, decimal_places=8)


class AddToCartRequestSerializer(serializers.Serializer):
    """Add-to-cart payload."""
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(required=False, min_value=1, default=1)
    source = serializers.CharField(required=False, allow_blank=True)
    merchant_id = serializers.IntegerField(required=False, allow_null=True)


class CartQuantitySerializer(serializers.Serializer):
    """Cart quantity update payload."""
    quantity = serializers.IntegerField(min_value=0)


class CheckoutRequestSerializer(serializers.Serializer):
    """Checkout request payload."""
    delivery_address = serializers.CharField()
    payment_method = serializers.CharField()


class UserActivityEntrySerializer(serializers.Serializer):
    """Serialized user activity row."""
    activity_type = serializers.CharField()
    created_at = serializers.DateTimeField()
    metadata = serializers.DictField()
    product = serializers.DictField(required=False)
    merchant = serializers.DictField(required=False)


class UserActivityResponseSerializer(serializers.Serializer):
    """User activity list response."""
    activities = UserActivityEntrySerializer(many=True)
