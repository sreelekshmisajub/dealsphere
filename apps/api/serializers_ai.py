"""
AI-powered API Serializers
Serializers for ML ranking, basket optimization, price prediction, and smart notifications
"""

from rest_framework import serializers
from django.contrib.auth.models import User
from ..core.models import Product, Offer, Merchant, Category, Brand, Notification

class RankedProductSerializer(serializers.ModelSerializer):
    """Serializer for AI-ranked products"""
    ml_score = serializers.FloatField(read_only=True)
    rank_position = serializers.IntegerField(read_only=True)
    best_offer_price = serializers.SerializerMethodField()
    best_offer_merchant = serializers.SerializerMethodField()
    delivery_time = serializers.SerializerMethodField()
    discount_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'category', 'brand', 'image_url', 'description',
            'amazon_price', 'rating', 'reviews_count',
            'ml_score', 'rank_position', 'best_offer_price',
            'best_offer_merchant', 'delivery_time', 'discount_percentage'
        ]
        depth = 1
    
    def get_best_offer_price(self, obj):
        """Get best offer price"""
        best_offer = Offer.objects.filter(product=obj).order_by('price').first()
        return float(best_offer.price) if best_offer else None
    
    def get_best_offer_merchant(self, obj):
        """Get best offer merchant"""
        best_offer = Offer.objects.filter(product=obj).order_by('price').first()
        return best_offer.merchant.shop_name if best_offer else None
    
    def get_delivery_time(self, obj):
        """Get best offer delivery time"""
        best_offer = Offer.objects.filter(product=obj).order_by('price').first()
        return best_offer.delivery_time_hours if best_offer else None
    
    def get_discount_percentage(self, obj):
        """Get best offer discount percentage"""
        best_offer = Offer.objects.filter(product=obj).order_by('price').first()
        return best_offer.discount_percentage if best_offer else None

class BasketOptimizationSerializer(serializers.Serializer):
    """Serializer for basket optimization results"""
    success = serializers.BooleanField()
    message = serializers.CharField()
    current_total = serializers.DecimalField(max_digits=10, decimal_places=2)
    optimized_total = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_savings = serializers.DecimalField(max_digits=10, decimal_places=2)
    savings_percentage = serializers.DecimalField(max_digits=5, decimal_places=2)
    recommendations = serializers.ListField(child=serializers.DictField())
    optimization_strategy = serializers.CharField()
    split_purchase = serializers.DictField()
    single_store = serializers.DictField()

class PricePredictionSerializer(serializers.Serializer):
    """Serializer for price prediction results"""
    success = serializers.BooleanField()
    message = serializers.CharField()
    predictions = serializers.DictField(
        child=serializers.DictField(
            child=serializers.FloatField()
        )
    )

class BarcodeSearchResultSerializer(serializers.Serializer):
    """Serializer for individual barcode search result"""
    id = serializers.IntegerField()
    name = serializers.CharField()
    category = serializers.CharField()
    brand = serializers.CharField()
    image_url = serializers.URLField()
    current_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    best_offer = serializers.DictField()
    match_confidence = serializers.FloatField()
    match_type = serializers.CharField()
    rating = serializers.FloatField()
    reviews_count = serializers.IntegerField()

class BarcodeSearchSerializer(serializers.Serializer):
    """Serializer for barcode search results"""
    success = serializers.BooleanField()
    found = serializers.BooleanField()
    products = BarcodeSearchResultSerializer(many=True)
    barcode_info = serializers.DictField()
    barcode_value = serializers.CharField()
    suggestions = serializers.ListField(child=serializers.CharField())
    message = serializers.CharField()

class ProductIdentificationResultSerializer(serializers.Serializer):
    """Serializer for individual product identification result"""
    id = serializers.IntegerField()
    name = serializers.CharField()
    category = serializers.CharField()
    brand = serializers.CharField()
    image_url = serializers.URLField()
    current_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    best_offer = serializers.DictField()
    match_score = serializers.FloatField()
    identification_confidence = serializers.FloatField()
    rating = serializers.FloatField()
    reviews_count = serializers.IntegerField()

class ProductIdentificationSerializer(serializers.Serializer):
    """Serializer for product identification results"""
    success = serializers.BooleanField()
    found = serializers.BooleanField()
    products = ProductIdentificationResultSerializer(many=True)
    identification_info = serializers.DictField()
    suggestions = serializers.ListField(child=serializers.CharField())
    message = serializers.CharField()

class NotificationSerializer(serializers.ModelSerializer):
    """Serializer for smart notifications"""
    product_info = serializers.SerializerMethodField()
    
    class Meta:
        model = Notification
        fields = [
            'id', 'title', 'message', 'notification_type',
            'priority', 'is_read', 'created_at', 'product_info'
        ]
    
    def get_product_info(self, obj):
        """Get product information if available"""
        if obj.product:
            return {
                'id': obj.product.id,
                'name': obj.product.name,
                'image_url': obj.product.image_url
            }
        return None

class SmartNotificationSerializer(serializers.Serializer):
    """Serializer for smart notifications (including unsaved AI notifications)"""
    id = serializers.IntegerField(allow_null=True)
    title = serializers.CharField()
    message = serializers.CharField()
    type = serializers.CharField()
    priority = serializers.CharField()
    is_read = serializers.BooleanField()
    created_at = serializers.DateTimeField(allow_null=True)
    product = serializers.DictField(allow_null=True)
    data = serializers.DictField()

class RecommendationSerializer(serializers.Serializer):
    """Serializer for personalized recommendations"""
    id = serializers.IntegerField()
    name = serializers.CharField()
    category = serializers.CharField()
    brand = serializers.CharField()
    image_url = serializers.URLField()
    current_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    best_offer = serializers.DictField()
    rating = serializers.FloatField()
    reviews_count = serializers.IntegerField()
    recommendation_score = serializers.FloatField()

class PersonalizedRecommendationsSerializer(serializers.Serializer):
    """Serializer for personalized recommendations results"""
    success = serializers.BooleanField()
    message = serializers.CharField()
    recommendations = RecommendationSerializer(many=True)

class AIInsightSerializer(serializers.Serializer):
    """Serializer for AI insights"""
    search_trends = serializers.DictField()
    price_savings = serializers.DictField()
    recommendation_accuracy = serializers.DictField()
    engagement_score = serializers.FloatField()
    next_actions = serializers.ListField(child=serializers.DictField())

class AIInsightsResponseSerializer(serializers.Serializer):
    """Serializer for AI insights response"""
    success = serializers.BooleanField()
    message = serializers.CharField()
    insights = AIInsightSerializer()
