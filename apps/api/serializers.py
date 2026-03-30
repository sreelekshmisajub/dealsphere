"""
Serializers for API app
"""

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from apps.core.models import Product, Offer, Notification, DealLock, PriceAlert, PriceMatchRequest
# from ai_engine.models.basket_optimizer import OptimizationResult  # Temporarily disabled

class ProductSearchSerializer(serializers.ModelSerializer):
    """Product search serializer for API"""
    best_offer = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    price_range = serializers.SerializerMethodField()
    offers_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        ref_name = 'ApiProductSearch'
        fields = ['id', 'name', 'category', 'brand', 'barcode', 'image_url', 
                 'best_offer', 'rating', 'price_range', 'offers_count', 'created_at']

    @extend_schema_field(serializers.DictField(allow_null=True))
    def get_best_offer(self, obj):
        """Get best offer for product"""
        best_offer = obj.offers.filter(is_active=True).order_by('price').first()
        if best_offer:
            return {
                'id': best_offer.id,
                'price': float(best_offer.price),
                'original_price': float(best_offer.original_price) if best_offer.original_price else None,
                'merchant': best_offer.merchant.shop_name,
                'merchant_id': best_offer.merchant.id,
                'delivery_time_hours': best_offer.delivery_time_hours,
                'delivery_cost': float(best_offer.delivery_cost),
                'discount_percentage': best_offer.discount_percentage,
                'rating': float(best_offer.merchant.rating),
                'verified': best_offer.merchant.verified,
                'source': 'local',
                'source_icon': 'fas fa-store'
            }

        online_sources = []
        if obj.amazon_price is not None:
            online_sources.append({
                'id': None,
                'price': float(obj.amazon_price),
                'original_price': float(obj.amazon_price),
                'merchant': 'Amazon',
                'merchant_id': None,
                'delivery_time_hours': 24,
                'delivery_cost': 0.0,
                'discount_percentage': None,
                'rating': float(obj.amazon_rating) if obj.amazon_rating is not None else None,
                'verified': True,
                'source': 'amazon',
                'source_icon': 'fab fa-amazon'
            })
        if obj.flipkart_price is not None:
            online_sources.append({
                'id': None,
                'price': float(obj.flipkart_price),
                'original_price': float(obj.flipkart_price),
                'merchant': 'Flipkart',
                'merchant_id': None,
                'delivery_time_hours': 48,
                'delivery_cost': 0.0,
                'discount_percentage': None,
                'rating': float(obj.flipkart_rating) if obj.flipkart_rating is not None else None,
                'verified': True,
                'source': 'flipkart',
                'source_icon': 'fas fa-bag-shopping'
            })
        if obj.myntra_price is not None:
            online_sources.append({
                'id': None,
                'price': float(obj.myntra_price),
                'original_price': float(obj.myntra_price),
                'merchant': 'Myntra',
                'merchant_id': None,
                'delivery_time_hours': 36,
                'delivery_cost': 0.0,
                'discount_percentage': None,
                'rating': float(obj.myntra_rating) if obj.myntra_rating is not None else None,
                'verified': True,
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

    @extend_schema_field(serializers.IntegerField())
    def get_offers_count(self, obj):
        """Get offers count"""
        return obj.offers.filter(is_active=True).count()

class RankedProductSerializer(serializers.Serializer):
    """Ranked product serializer"""
    id = serializers.CharField()
    name = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    distance = serializers.FloatField()
    delivery_time = serializers.FloatField()
    reliability = serializers.FloatField()
    ml_score = serializers.FloatField()
    category = serializers.CharField(allow_null=True)
    brand = serializers.CharField(allow_null=True)
    image_url = serializers.URLField(allow_null=True)
    merchant = serializers.CharField(allow_null=True)


class RankedProductsRequestSerializer(serializers.Serializer):
    """Request payload for ranked product scoring."""
    products = serializers.ListField(child=serializers.DictField(), allow_empty=False)

class BasketOptimizationSerializer(serializers.Serializer):
    """Basket optimization result serializer"""
    best_option = serializers.DictField()
    all_options = serializers.ListField()
    baseline_cost = serializers.FloatField()
    max_savings = serializers.FloatField()
    product_count = serializers.IntegerField()
    budget = serializers.FloatField(allow_null=True)
    within_budget = serializers.BooleanField(allow_null=True)
    recommendations = serializers.ListField()


class BasketOptimizationRequestSerializer(serializers.Serializer):
    """Request payload for basket optimization."""
    products = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    quantities = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False)
    budget = serializers.FloatField(required=False, allow_null=True)
    user_lat = serializers.FloatField(required=False, allow_null=True)
    user_lng = serializers.FloatField(required=False, allow_null=True)

class PricePredictionSerializer(serializers.Serializer):
    """Price prediction serializer"""
    status = serializers.CharField()
    product_id = serializers.CharField()
    product_name = serializers.CharField()
    current_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    predictions = serializers.ListField()
    dates = serializers.ListField()
    confidence_intervals = serializers.ListField()
    trend = serializers.CharField()
    best_day_to_buy = serializers.DictField()
    confidence_level = serializers.CharField(required=False, allow_null=True)
    fallback_basis = serializers.DictField(required=False)
    message = serializers.CharField(required=False, allow_blank=True)


class PricePredictionRequestSerializer(serializers.Serializer):
    """Request payload for price prediction."""
    product_id = serializers.IntegerField()
    days_ahead = serializers.IntegerField(required=False, min_value=1, max_value=30, default=7)

class DropProbabilitySerializer(serializers.Serializer):
    """Price drop probability serializer"""
    product_id = serializers.CharField()
    probability_of_drop = serializers.FloatField()
    expected_drop_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    expected_drop_percentage = serializers.FloatField()
    recommendation = serializers.CharField()

class NotificationSerializer(serializers.ModelSerializer):
    """Notification serializer"""
    time_ago = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ['id', 'title', 'message', 'notification_type', 'is_read', 'time_ago', 'created_at']
        read_only_fields = ['id', 'created_at']

    @extend_schema_field(serializers.CharField())
    def get_time_ago(self, obj):
        """Get human readable time ago"""
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        diff = now - obj.created_at
        
        if diff < timedelta(minutes=1):
            return "Just now"
        elif diff < timedelta(hours=1):
            return f"{diff.seconds // 60} minutes ago"
        elif diff < timedelta(days=1):
            return f"{diff.seconds // 3600} hours ago"
        elif diff < timedelta(days=30):
            return f"{diff.days} days ago"
        else:
            return obj.created_at.strftime('%Y-%m-%d')

class ProductIdentificationSerializer(serializers.Serializer):
    """Product identification result serializer"""
    status = serializers.CharField()
    predicted_category = serializers.CharField(allow_null=True)
    predicted_supercategory = serializers.CharField(required=False, allow_null=True)
    confidence = serializers.FloatField()
    all_predictions = serializers.ListField()
    matching_products = serializers.ListField()
    reference_matches = serializers.ListField(required=False)
    dataset_reference_images = serializers.IntegerField(required=False)
    message = serializers.CharField(required=False, allow_blank=True)


class ProductIdentificationUploadSerializer(serializers.Serializer):
    """Image upload payload for product identification."""
    image = serializers.ImageField()

class BarcodeSearchResultSerializer(serializers.Serializer):
    """Barcode search result serializer"""
    found = serializers.BooleanField()
    match_type = serializers.CharField(allow_null=True)
    product = serializers.DictField(allow_null=True)
    barcode = serializers.CharField()
    confidence = serializers.FloatField(allow_null=True)
    similar_products = serializers.ListField()
    price_comparison = serializers.ListField()
    message = serializers.CharField(allow_null=True)
    error = serializers.CharField(allow_null=True)


class BarcodeSearchRequestSerializer(serializers.Serializer):
    """Request payload for barcode search."""
    barcode = serializers.CharField()


class AmazonReviewSerializer(serializers.Serializer):
    """Single normalized Amazon review row."""
    review_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    review_title = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    review_comment = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    review_star_rating = serializers.FloatField(required=False, allow_null=True)
    review_link = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    review_author = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    review_author_avatar = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    review_date = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    is_verified_purchase = serializers.BooleanField(required=False)
    helpful_vote_statement = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    review_images = serializers.ListField(child=serializers.URLField(), required=False)


class AmazonProductReviewsSerializer(serializers.Serializer):
    """Amazon review feed for a product row."""
    status = serializers.CharField()
    message = serializers.CharField(required=False, allow_blank=True)
    product_id = serializers.IntegerField(required=False)
    product_name = serializers.CharField(required=False)
    asin = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    country = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    domain = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    request_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    rating_distribution = serializers.DictField(child=serializers.IntegerField(), required=False)
    review_count = serializers.IntegerField(required=False)
    reviews = AmazonReviewSerializer(many=True, required=False)
    source = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    provider_status_code = serializers.IntegerField(required=False)
    provider_error = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class AmazonProductSnapshotSerializer(serializers.Serializer):
    """Normalized live Amazon product snapshot payload."""
    status = serializers.CharField()
    message = serializers.CharField(required=False, allow_blank=True)
    product_id = serializers.IntegerField(required=False)
    product_name = serializers.CharField(required=False)
    asin = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    domain = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    provider_request_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    live_title = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    live_brand = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    current_price = serializers.FloatField(required=False, allow_null=True)
    original_price = serializers.FloatField(required=False, allow_null=True)
    currency_symbol = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    currency_code = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    rating = serializers.FloatField(required=False, allow_null=True)
    ratings_total = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    availability = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    location = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    product_url = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    image_url = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    prime = serializers.BooleanField(required=False)
    amazon_choice = serializers.BooleanField(required=False)
    best_seller = serializers.BooleanField(required=False)
    sales_volume = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    features = serializers.ListField(child=serializers.CharField(), required=False)
    source = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    provider_status_code = serializers.IntegerField(required=False)
    provider_error = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class ExternalFemaleFootwearItemSerializer(serializers.Serializer):
    """Normalized female footwear feed row."""
    id = serializers.IntegerField()
    brand = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    description = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    image_url = serializers.URLField(required=False, allow_blank=True, allow_null=True)
    price_text = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    price_value = serializers.FloatField(required=False, allow_null=True)
    tag = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class ExternalFemaleFootwearFeedSerializer(serializers.Serializer):
    """Normalized female footwear feed payload."""
    status = serializers.CharField()
    message = serializers.CharField(required=False, allow_blank=True)
    items = ExternalFemaleFootwearItemSerializer(many=True, required=False)
    count = serializers.IntegerField(required=False)
    source = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    provider_status_code = serializers.IntegerField(required=False)
    provider_error = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class ExternalProductPriceHistoryPointSerializer(serializers.Serializer):
    """Single normalized price-history point."""
    date = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    price = serializers.FloatField()
    currency = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    label = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class ExternalProductPriceHistorySerializer(serializers.Serializer):
    """Normalized product price-history payload."""
    status = serializers.CharField()
    message = serializers.CharField(required=False, allow_blank=True)
    product_id = serializers.CharField(required=False)
    country = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    language = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    provider_request_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    title = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    brand = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    latest_price = serializers.FloatField(required=False, allow_null=True)
    lowest_price = serializers.FloatField(required=False, allow_null=True)
    highest_price = serializers.FloatField(required=False, allow_null=True)
    currency = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    point_count = serializers.IntegerField(required=False)
    history = ExternalProductPriceHistoryPointSerializer(many=True, required=False)
    source = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    provider_status_code = serializers.IntegerField(required=False)
    provider_error = serializers.CharField(required=False, allow_blank=True, allow_null=True)

class MarketInsightsSerializer(serializers.Serializer):
    """Market insights serializer"""
    total_products = serializers.IntegerField()
    price_trends = serializers.DictField()
    best_deals = serializers.ListField()
    price_drops_predicted = serializers.ListField()

class TrendingProductSerializer(serializers.Serializer):
    """Trending product serializer"""
    id = serializers.CharField()
    name = serializers.CharField()
    category = serializers.CharField()
    view_count = serializers.IntegerField()
    best_offer = serializers.DictField()
    image_url = serializers.URLField(allow_null=True)


class MarkNotificationReadRequestSerializer(serializers.Serializer):
    """Notification mark-read payload."""
    notification_id = serializers.IntegerField(required=False)
    mark_all = serializers.BooleanField(required=False, default=False)


class DealLockSerializer(serializers.ModelSerializer):
    """Deal lock serializer"""
    offer = serializers.SerializerMethodField()

    class Meta:
        model = DealLock
        fields = ['id', 'offer', 'locked_price', 'lock_duration_hours', 'locked_until', 'status', 'created_at']
        read_only_fields = ['id', 'created_at']

    @extend_schema_field(serializers.DictField())
    def get_offer(self, obj):
        return {
            'id': obj.offer.id,
            'product_name': obj.offer.product.name,
            'merchant_name': obj.offer.merchant.shop_name,
            'price': float(obj.offer.price),
        }


class PriceAlertSerializer(serializers.ModelSerializer):
    """Price alert serializer"""
    product = serializers.SerializerMethodField()

    class Meta:
        model = PriceAlert
        fields = ['id', 'product', 'target_price', 'is_active', 'last_notified_at', 'created_at']
        read_only_fields = ['id', 'created_at', 'last_notified_at']

    @extend_schema_field(serializers.DictField())
    def get_product(self, obj):
        return {
            'id': obj.product.id,
            'name': obj.product.name,
        }


class PriceMatchRequestSerializer(serializers.ModelSerializer):
    """Price match request serializer"""
    product = serializers.SerializerMethodField()
    merchant = serializers.SerializerMethodField()

    class Meta:
        model = PriceMatchRequest
        fields = [
            'id', 'product', 'merchant', 'requested_price', 'competitor_price',
            'competitor_source', 'status', 'response_message', 'created_at', 'expires_at',
        ]
        read_only_fields = ['id', 'status', 'response_message', 'created_at']

    @extend_schema_field(serializers.DictField())
    def get_product(self, obj):
        return {
            'id': obj.product.id,
            'name': obj.product.name,
        }

    @extend_schema_field(serializers.DictField())
    def get_merchant(self, obj):
        return {
            'id': obj.merchant.id,
            'shop_name': obj.merchant.shop_name,
        }


class ProductOffersComparisonSerializer(serializers.Serializer):
    """Online/offline offer comparison serializer"""
    product = serializers.DictField()
    online = serializers.ListField()
    offline = serializers.ListField()
    best_online = serializers.DictField(allow_null=True)
    best_offline = serializers.DictField(allow_null=True)
    recommendation = serializers.ChoiceField(choices=['online', 'offline', 'tie'])
