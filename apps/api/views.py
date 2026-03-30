"""
Main API views for DealSphere
"""

from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models import Q, Count, Avg, Min, Max
from django.utils import timezone
from django.core.exceptions import ValidationError
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
import logging

from apps.core.models import (
    Notification, Product, Offer, User, Cart, CartItem, UserActivity,
    DealLock, PriceAlert, PriceMatchRequest, Merchant,
)
from apps.core.runtime_config import get_ml_weights
from .external_feeds import ExternalFashionFeedService, RealTimeProductSearchService
from .serializers import (
    ProductSearchSerializer, RankedProductSerializer,
    BasketOptimizationSerializer, PricePredictionSerializer,
    NotificationSerializer, ProductIdentificationSerializer,
    ProductIdentificationUploadSerializer, BarcodeSearchResultSerializer,
    BarcodeSearchRequestSerializer, MarketInsightsSerializer,
    MarkNotificationReadRequestSerializer, RankedProductsRequestSerializer,
    BasketOptimizationRequestSerializer, PricePredictionRequestSerializer,
    AmazonProductReviewsSerializer,
    AmazonProductSnapshotSerializer,
    ExternalFemaleFootwearFeedSerializer,
    ExternalProductPriceHistorySerializer,
    DealLockSerializer, PriceAlertSerializer,
    PriceMatchRequestSerializer, ProductOffersComparisonSerializer,
)
from .ai_services import RealAIService
from apps.users.services import ProductService, SearchService

logger = logging.getLogger(__name__)

class ProductSearchView(generics.ListAPIView):
    """Product search API"""
    serializer_class = ProductSearchSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        query = self.request.query_params.get('q', '').strip()
        category = self.request.query_params.get('category', '').strip()
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        sort_by = self.request.query_params.get('sort_by', 'relevance')
        limit = int(self.request.query_params.get('limit', 20))
        
        # Search products
        queryset = SearchService.search_products(
            query=query,
            category=category,
            min_price=min_price,
            max_price=max_price,
            sort_by=sort_by,
            user=self.request.user
        )
        
        return queryset[:limit]

class GetRankedResultsView(APIView):
    """Get ranked results using ML"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=RankedProductsRequestSerializer,
        responses=inline_serializer(
            name="RankedProductsResponse",
            fields={
                "ranked_products": RankedProductSerializer(many=True),
                "feature_importance": serializers.DictField(),
                "total_products": serializers.IntegerField(),
            },
        ),
    )
    def post(self, request):
        try:
            products_data = request.data.get('products', [])
            
            if not products_data:
                return Response({'error': 'No products provided'}, status=status.HTTP_400_BAD_REQUEST)
            
            ranked_products = RealAIService.rank_products(products_data)
            feature_importance = get_ml_weights()
            
            # Log ranking activity
            UserActivity.objects.create(
                user=request.user,
                activity_type='product_ranking',
                metadata={
                    'product_count': len(products_data),
                    'feature_importance': feature_importance
                }
            )
            
            return Response({
                'ranked_products': ranked_products,
                'feature_importance': feature_importance,
                'total_products': len(ranked_products)
            })
            
        except Exception as e:
            logger.error(f"Error ranking products: {e}")
            return Response({'error': 'Failed to rank products'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class BasketOptimizationView(APIView):
    """Basket optimization API"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=BasketOptimizationRequestSerializer, responses=BasketOptimizationSerializer)
    def post(self, request):
        try:
            products = request.data.get('products', [])
            quantities = request.data.get('quantities', [])
            budget = request.data.get('budget')
            user_lat = request.data.get('user_lat')
            user_lng = request.data.get('user_lng')
            
            if not products or not quantities:
                return Response({'error': 'Products and quantities required'}, status=status.HTTP_400_BAD_REQUEST)
            
            if len(products) != len(quantities):
                return Response({'error': 'Products and quantities must have same length'}, status=status.HTTP_400_BAD_REQUEST)
            
            result = RealAIService.optimize_basket(products, quantities, budget)
            
            if not result.get('best_option'):
                return Response({'error': 'Optimization failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Log optimization activity
            UserActivity.objects.create(
                user=request.user,
                activity_type='basket_optimization',
                metadata={
                    'product_count': len(products),
                    'budget': budget,
                    'total_cost': result.get('best_option', {}).get('total_cost') if result.get('best_option') else None,
                    'savings': result.get('best_option', {}).get('savings') if result.get('best_option') else None
                }
            )
            
            # Serialize response
            serializer = BasketOptimizationSerializer(result)
            
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Error optimizing basket: {e}")
            return Response({'error': 'Failed to optimize basket'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PricePredictionView(APIView):
    """Price prediction API"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=PricePredictionRequestSerializer,
        responses=inline_serializer(
            name="PricePredictionResponse",
            fields={
                "price_prediction": PricePredictionSerializer(),
                "drop_probability": serializers.FloatField(allow_null=True),
            },
        ),
    )
    def post(self, request):
        try:
            product_id = request.data.get('product_id')
            days_ahead = request.data.get('days_ahead', 7)
            
            if not product_id:
                return Response({'error': 'Product ID required'}, status=status.HTTP_400_BAD_REQUEST)
            
            prediction = RealAIService.predict_price(int(product_id), int(days_ahead))
            
            if not prediction:
                return Response({'error': 'Product not found or prediction failed'}, status=status.HTTP_404_NOT_FOUND)
            
            # Log prediction activity
            UserActivity.objects.create(
                user=request.user,
                activity_type='price_prediction',
                metadata={
                    'product_id': product_id,
                    'days_ahead': days_ahead,
                    'trend': prediction.get('trend'),
                    'drop_probability': 0
                }
            )
            
            return Response({
                'price_prediction': prediction,
                'drop_probability': None
            })
            
        except Exception as e:
            logger.error(f"Error predicting prices: {e}")
            return Response({'error': 'Failed to predict prices'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ProductIdentificationView(APIView):
    """Product identification from image"""
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=ProductIdentificationUploadSerializer, responses=ProductIdentificationSerializer)
    def post(self, request):
        try:
            image_file = request.FILES.get('image')
            
            if not image_file:
                return Response({'error': 'No image provided'}, status=status.HTTP_400_BAD_REQUEST)

            result = RealAIService.identify_product(image_file)
            matching_products = result.get("matching_products", [])
            result["matching_products"] = ProductSearchSerializer(matching_products, many=True).data
            serializer = ProductIdentificationSerializer(data=result)
            serializer.is_valid(raise_exception=True)
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Error identifying product: {e}")
            return Response({'error': 'Failed to identify product'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class BarcodeSearchView(APIView):
    """Barcode search API"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(request=BarcodeSearchRequestSerializer, responses=BarcodeSearchResultSerializer)
    def post(self, request):
        try:
            barcode = request.data.get('barcode')
            
            if not barcode:
                return Response({'error': 'Barcode required'}, status=status.HTTP_400_BAD_REQUEST)
            
            result = RealAIService.barcode_search(barcode)
            
            # Log barcode search activity
            UserActivity.objects.create(
                user=request.user,
                activity_type='barcode_search',
                metadata={
                    'barcode': barcode,
                    'found': result.get('found', False)
                }
            )
            
            return Response(result)
            
        except Exception as e:
            logger.error(f"Error searching barcode: {e}")
            return Response({'error': 'Failed to search barcode'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class NotificationView(generics.ListAPIView):
    """Get user notifications"""
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        notification_type = self.request.query_params.get('type')
        is_read = self.request.query_params.get('is_read')
        limit = int(self.request.query_params.get('limit', 20))
        
        queryset = user.notifications.all()
        
        if notification_type:
            queryset = queryset.filter(notification_type=notification_type)
        
        if is_read is not None:
            queryset = queryset.filter(is_read=is_read.lower() == 'true')
        
        return queryset.order_by('-created_at')[:limit]

class MarkNotificationReadView(APIView):
    """Mark notification as read"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=MarkNotificationReadRequestSerializer,
        responses=inline_serializer(
            name="NotificationMarkReadResponse",
            fields={
                "message": serializers.CharField(),
                "marked_count": serializers.IntegerField(required=False),
                "notification_id": serializers.IntegerField(required=False),
            },
        ),
    )
    def post(self, request):
        try:
            notification_id = request.data.get('notification_id')
            mark_all = request.data.get('mark_all', False)
            
            if mark_all:
                # Mark all notifications as read
                count = request.user.notifications.filter(is_read=False).update(is_read=True)
                
                return Response({
                    'message': f'Marked {count} notifications as read',
                    'marked_count': count
                })
            
            elif notification_id:
                # Mark specific notification as read
                try:
                    notification = request.user.notifications.get(id=notification_id)
                    notification.is_read = True
                    notification.save()
                    
                    return Response({
                        'message': 'Notification marked as read',
                        'notification_id': notification_id
                    })
                    
                except Notification.DoesNotExist:
                    return Response({'error': 'Notification not found'}, status=status.HTTP_404_NOT_FOUND)
            
            else:
                return Response({'error': 'Either notification_id or mark_all required'}, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            logger.error(f"Error marking notification read: {e}")
            return Response({'error': 'Failed to mark notification read'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MarketInsightsView(APIView):
    """Get market insights"""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=MarketInsightsSerializer)
    def get(self, request):
        try:
            category = request.query_params.get('category')
            
            insights = RealAIService.market_insights(category)
            
            return Response(insights)
            
        except Exception as e:
            logger.error(f"Error getting market insights: {e}")
            return Response({'error': 'Failed to get market insights'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TrendingProductsView(generics.ListAPIView):
    """Get trending products"""
    serializer_class = ProductSearchSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        limit = int(self.request.query_params.get('limit', 10))
        return SearchService.get_trending_products(limit)

class SimilarProductsView(generics.ListAPIView):
    """Get similar products"""
    serializer_class = ProductSearchSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        product_id = self.kwargs.get('product_id')
        limit = int(self.request.query_params.get('limit', 5))
        return SearchService.get_similar_products(product_id, limit)


class AmazonProductReviewsView(APIView):
    """Get live Amazon reviews for the Amazon-linked product row."""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=AmazonProductReviewsSerializer)
    def get(self, request, product_id):
        try:
            limit = max(1, min(int(request.query_params.get("limit", 5) or 5), 10))
            result = RealAIService.get_amazon_reviews(product_id, limit=limit)

            if result.get("status") == "product_not_found":
                return Response(result, status=status.HTTP_404_NOT_FOUND)

            if result.get("status") in {"api_error", "transport_error", "parse_error"}:
                response_status = status.HTTP_502_BAD_GATEWAY
            else:
                response_status = status.HTTP_200_OK

            serializer = AmazonProductReviewsSerializer(data=result)
            serializer.is_valid(raise_exception=True)
            return Response(serializer.data, status=response_status)

        except Exception as e:
            logger.error(f"Error getting Amazon reviews: {e}")
            return Response({'error': 'Failed to get Amazon reviews'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AmazonProductSnapshotView(APIView):
    """Get live Amazon product pricing and metadata snapshot."""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=AmazonProductSnapshotSerializer)
    def get(self, request, product_id):
        try:
            result = RealAIService.get_amazon_product_snapshot(product_id)

            if result.get("status") == "product_not_found":
                response_status = status.HTTP_404_NOT_FOUND
            elif result.get("status") in {"provider_access_denied", "api_error", "transport_error", "parse_error"}:
                response_status = status.HTTP_502_BAD_GATEWAY
            else:
                response_status = status.HTTP_200_OK

            serializer = AmazonProductSnapshotSerializer(data=result)
            serializer.is_valid(raise_exception=True)
            return Response(serializer.data, status=response_status)

        except Exception as e:
            logger.error(f"Error getting Amazon product snapshot: {e}")
            return Response({'error': 'Failed to get Amazon product snapshot'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ExternalFemaleFootwearFeedView(APIView):
    """Get normalized female footwear feed rows."""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=ExternalFemaleFootwearFeedSerializer)
    def get(self, request):
        try:
            limit = max(1, min(int(request.query_params.get("limit", 48) or 48), 100))
            result = ExternalFashionFeedService.get_female_footwear(limit=limit)
            response_status = status.HTTP_200_OK if result.get("status") == "ok" else status.HTTP_502_BAD_GATEWAY
            serializer = ExternalFemaleFootwearFeedSerializer(data=result)
            serializer.is_valid(raise_exception=True)
            return Response(serializer.data, status=response_status)
        except Exception as e:
            logger.error(f"Error getting female footwear feed: {e}")
            return Response({'error': 'Failed to get female footwear feed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ExternalProductPriceHistoryView(APIView):
    """Get normalized external product price history from RapidAPI."""
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(responses=ExternalProductPriceHistorySerializer)
    def get(self, request):
        try:
            provider_product_id = str(request.query_params.get("product_id", "")).strip()
            country = str(request.query_params.get("country", "us")).strip().lower() or "us"
            language = str(request.query_params.get("language", "en")).strip().lower() or "en"

            if not provider_product_id:
                return Response(
                    {"error": "product_id query parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            result = RealTimeProductSearchService.get_product_price_history(
                provider_product_id=provider_product_id,
                country=country,
                language=language,
            )

            if result.get("status") in {"api_error", "transport_error", "parse_error"}:
                response_status = status.HTTP_502_BAD_GATEWAY
            else:
                response_status = status.HTTP_200_OK

            serializer = ExternalProductPriceHistorySerializer(data=result)
            serializer.is_valid(raise_exception=True)
            return Response(serializer.data, status=response_status)
        except Exception as e:
            logger.error(f"Error getting external product price history: {e}")
            return Response(
                {"error": "Failed to get external product price history"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

@extend_schema(
    responses=inline_serializer(
        name="PriceComparisonResponse",
        fields={
            "amazon": serializers.DictField(),
            "flipkart": serializers.DictField(),
            "myntra": serializers.DictField(),
            "local_stores": serializers.ListField(),
        },
    )
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_price_comparison(request, product_id):
    """Get price comparison for product"""
    try:
        comparison = ProductService.get_price_comparison(product_id)
        
        if not comparison:
            return Response({'error': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)
        
        return Response(comparison)
        
    except Exception as e:
        logger.error(f"Error getting price comparison: {e}")
        return Response({'error': 'Failed to get price comparison'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@extend_schema(
    responses=inline_serializer(
        name="ProductDetailsResponse",
        fields={
            "id": serializers.IntegerField(),
            "name": serializers.CharField(),
            "barcode": serializers.CharField(allow_blank=True, allow_null=True),
            "image_url": serializers.URLField(allow_blank=True, allow_null=True),
            "best_offer": serializers.DictField(required=False),
            "rating": serializers.FloatField(required=False, allow_null=True),
            "price_range": serializers.DictField(required=False, allow_null=True),
            "offers": serializers.ListField(),
            "price_history": serializers.ListField(),
        },
    )
)
@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_product_details(request, product_id):
    """Get detailed product information"""
    try:
        details = ProductService.get_product_details(product_id, request.user)
        
        if not details:
            return Response({'error': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Serialize the response
        product_data = ProductSearchSerializer(details['product']).data
        
        # Add offers
        offers_data = []
        for offer in details['offers']:
            offers_data.append({
                'id': offer.id,
                'merchant': offer.merchant.shop_name,
                'price': float(offer.price),
                'original_price': float(offer.original_price) if offer.original_price else None,
                'discount_percentage': offer.discount_percentage,
                'delivery_time_hours': offer.delivery_time_hours,
                'delivery_cost': float(offer.delivery_cost),
                'stock_quantity': offer.stock_quantity,
                'rating': float(offer.merchant.rating),
                'verified': offer.merchant.verified
            })
        
        product_data['offers'] = offers_data
        product_data['price_history'] = [
            {
                'source': ph.source,
                'price': float(ph.price),
                'date': ph.created_at.date()
            }
            for ph in details['price_history'][:30]
        ]
        
        return Response(product_data)
        
    except Exception as e:
        logger.error(f"Error getting product details: {e}")
        return Response({'error': 'Failed to get product details'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------------------------------------------------------------------------
# Feature 1: Smart Cart Basket
# ---------------------------------------------------------------------------

class SmartCartBasketView(APIView):
    """POST /api/ai/smart-basket/ - optimise user's current cart items"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            user = request.user
            try:
                cart = Cart.objects.prefetch_related(
                    'items__product', 'items__merchant'
                ).get(user=user)
            except Cart.DoesNotExist:
                return Response({'error': 'Cart not found'}, status=status.HTTP_404_NOT_FOUND)

            cart_items = list(cart.items.all())
            if not cart_items:
                return Response({'error': 'Cart is empty'}, status=status.HTTP_400_BAD_REQUEST)

            per_item_breakdown = []
            total_cheapest = 0.0

            for item in cart_items:
                product = item.product
                qty = item.quantity
                options = []

                # Local merchant offers
                for offer in product.offers.filter(is_active=True).select_related('merchant'):
                    options.append({
                        'source': 'local',
                        'source_name': offer.merchant.shop_name,
                        'price': float(offer.price),
                        'delivery_time_hours': offer.delivery_time_hours,
                        'delivery_cost': float(offer.delivery_cost),
                        'offer_id': offer.id,
                        'merchant_id': offer.merchant.id,
                    })

                # Online sources
                if product.amazon_price is not None:
                    options.append({
                        'source': 'amazon',
                        'source_name': 'Amazon',
                        'price': float(product.amazon_price),
                        'delivery_time_hours': 24,
                        'delivery_cost': 0.0,
                        'url': product.amazon_url,
                    })
                if product.flipkart_price is not None:
                    options.append({
                        'source': 'flipkart',
                        'source_name': 'Flipkart',
                        'price': float(product.flipkart_price),
                        'delivery_time_hours': 48,
                        'delivery_cost': 0.0,
                        'url': product.flipkart_url,
                    })
                if product.myntra_price is not None:
                    options.append({
                        'source': 'myntra',
                        'source_name': 'Myntra',
                        'price': float(product.myntra_price),
                        'delivery_time_hours': 36,
                        'delivery_cost': 0.0,
                        'url': product.myntra_url,
                    })

                if not options:
                    best = None
                    item_cheapest = 0.0
                else:
                    options_sorted = sorted(options, key=lambda o: o['price'])
                    best = options_sorted[0]
                    item_cheapest = best['price'] * qty

                total_cheapest += item_cheapest

                per_item_breakdown.append({
                    'product_id': product.id,
                    'product_name': product.name,
                    'quantity': qty,
                    'best_option': best,
                    'all_options': options,
                    'item_total': item_cheapest,
                })

            # Estimate savings vs buying all from cheapest single store
            all_prices = [
                o['price']
                for entry in per_item_breakdown
                for o in entry['all_options']
            ]
            if all_prices:
                baseline = sum(
                    min((o['price'] for o in entry['all_options']), default=0) * entry['quantity']
                    if entry['all_options'] else 0
                    for entry in per_item_breakdown
                )
            else:
                baseline = total_cheapest

            estimated_savings = max(0.0, baseline - total_cheapest)

            return Response({
                'items': per_item_breakdown,
                'total_cheapest': round(total_cheapest, 2),
                'estimated_savings': round(estimated_savings, 2),
                'item_count': len(per_item_breakdown),
                'strategy': 'Split purchase across cheapest available sources per item.',
            })

        except Exception as e:
            logger.error(f"Error in smart basket: {e}")
            return Response({'error': 'Failed to optimise basket'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------------------------------------------------------------------------
# Feature 2: Deal Lock
# ---------------------------------------------------------------------------

class DealLockCreateView(APIView):
    """POST /api/deals/lock/"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            offer_id = request.data.get('offer_id')
            lock_hours = int(request.data.get('lock_hours', 24))

            if not offer_id:
                return Response({'error': 'offer_id is required'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                offer = Offer.objects.select_related('product', 'merchant').get(id=offer_id, is_active=True)
            except Offer.DoesNotExist:
                return Response({'error': 'Offer not found or inactive'}, status=status.HTTP_404_NOT_FOUND)

            user = request.user
            if DealLock.objects.filter(user=user, offer=offer, status='active').exists():
                return Response({'error': 'You already have an active lock on this offer'}, status=status.HTTP_400_BAD_REQUEST)

            locked_until = timezone.now() + timezone.timedelta(hours=lock_hours)
            deal_lock = DealLock.objects.create(
                user=user,
                offer=offer,
                locked_price=offer.price,
                lock_duration_hours=lock_hours,
                locked_until=locked_until,
                status='active',
            )

            # Notify user
            try:
                from apps.core.notification_service import NotificationService
                NotificationService.notify_deal_lock(user, deal_lock)
            except Exception as notify_err:
                logger.warning(f"Deal lock notification failed: {notify_err}")

            return Response(DealLockSerializer(deal_lock).data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error creating deal lock: {e}")
            return Response({'error': 'Failed to create deal lock'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DealLockListView(generics.ListAPIView):
    """GET /api/deals/locks/"""
    serializer_class = DealLockSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = DealLock.objects.filter(user=self.request.user).select_related(
            'offer__product', 'offer__merchant'
        )
        lock_status = self.request.query_params.get('status')
        if lock_status:
            qs = qs.filter(status=lock_status)
        return qs


class DealLockCancelView(APIView):
    """DELETE /api/deals/locks/{id}/"""
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        try:
            deal_lock = DealLock.objects.get(id=pk, user=request.user)
        except DealLock.DoesNotExist:
            return Response({'error': 'Deal lock not found'}, status=status.HTTP_404_NOT_FOUND)

        if deal_lock.status != 'active':
            return Response({'error': f'Cannot cancel a lock with status "{deal_lock.status}"'}, status=status.HTTP_400_BAD_REQUEST)

        deal_lock.status = 'cancelled'
        deal_lock.save(update_fields=['status', 'updated_at'])
        return Response({'message': 'Deal lock cancelled'}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Feature 3: Product ML Ranking endpoint
# ---------------------------------------------------------------------------

class ProductRankingView(APIView):
    """GET /api/products/{product_id}/ranking/ - ML-ranked offers for a product"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            ranked = []

            # Local offers
            for offer in product.offers.filter(is_active=True).select_related('merchant'):
                price = float(offer.price)
                delivery = offer.delivery_time_hours
                rating = float(offer.merchant.rating) if offer.merchant.rating else 0.0
                verified = offer.merchant.verified
                score = (
                    (1 / price * 0.4) +
                    (1 / (delivery + 1) * 0.3) +
                    (rating / 5 * 0.2) +
                    ((1.0 if verified else 0.5) * 0.1)
                )
                ranked.append({
                    'source': 'local',
                    'source_name': offer.merchant.shop_name,
                    'offer_id': offer.id,
                    'merchant_id': offer.merchant.id,
                    'price': price,
                    'delivery_time_hours': delivery,
                    'delivery_cost': float(offer.delivery_cost),
                    'rating': rating,
                    'verified': verified,
                    'ml_score': round(score, 6),
                })

            # Online sources
            online_defaults = [
                ('amazon', 'Amazon', product.amazon_price, 24, product.amazon_url),
                ('flipkart', 'Flipkart', product.flipkart_price, 48, product.flipkart_url),
                ('myntra', 'Myntra', product.myntra_price, 36, product.myntra_url),
            ]
            for src, name, price_val, delivery, url in online_defaults:
                if price_val is None:
                    continue
                price = float(price_val)
                score = (
                    (1 / price * 0.4) +
                    (1 / (delivery + 1) * 0.3) +
                    (5.0 / 5 * 0.2) +
                    (1.0 * 0.1)
                )
                ranked.append({
                    'source': src,
                    'source_name': name,
                    'offer_id': None,
                    'merchant_id': None,
                    'price': price,
                    'delivery_time_hours': delivery,
                    'delivery_cost': 0.0,
                    'rating': None,
                    'verified': True,
                    'url': url,
                    'ml_score': round(score, 6),
                })

            ranked.sort(key=lambda x: x['ml_score'], reverse=True)

            return Response({
                'product_id': product.id,
                'product_name': product.name,
                'ranked_offers': ranked,
                'total': len(ranked),
            })

        except Exception as e:
            logger.error(f"Error ranking product offers: {e}")
            return Response({'error': 'Failed to rank offers'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------------------------------------------------------------------------
# Feature 5: Online/Offline Offer Comparison
# ---------------------------------------------------------------------------

class ProductOffersView(APIView):
    """GET /api/products/{product_id}/offers/"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, product_id):
        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            online = []
            if product.amazon_price is not None:
                online.append({'source': 'amazon', 'price': float(product.amazon_price), 'url': product.amazon_url, 'delivery_time_hours': 24})
            if product.flipkart_price is not None:
                online.append({'source': 'flipkart', 'price': float(product.flipkart_price), 'url': product.flipkart_url, 'delivery_time_hours': 48})
            if product.myntra_price is not None:
                online.append({'source': 'myntra', 'price': float(product.myntra_price), 'url': product.myntra_url, 'delivery_time_hours': 36})

            offline = []
            for offer in product.offers.filter(is_active=True).select_related('merchant'):
                offline.append({
                    'offer_id': offer.id,
                    'merchant': offer.merchant.shop_name,
                    'merchant_id': offer.merchant.id,
                    'price': float(offer.price),
                    'delivery_time_hours': offer.delivery_time_hours,
                    'delivery_cost': float(offer.delivery_cost),
                    'rating': float(offer.merchant.rating),
                    'verified': offer.merchant.verified,
                })

            best_online = min(online, key=lambda x: x['price']) if online else None
            best_offline = min(offline, key=lambda x: x['price']) if offline else None

            if best_online and best_offline:
                recommendation = 'online' if best_online['price'] < best_offline['price'] else (
                    'offline' if best_offline['price'] < best_online['price'] else 'tie'
                )
            elif best_online:
                recommendation = 'online'
            elif best_offline:
                recommendation = 'offline'
            else:
                recommendation = 'tie'

            product_data = ProductSearchSerializer(product).data
            return Response({
                'product': product_data,
                'online': online,
                'offline': offline,
                'best_online': best_online,
                'best_offline': best_offline,
                'recommendation': recommendation,
            })

        except Exception as e:
            logger.error(f"Error getting product offers: {e}")
            return Response({'error': 'Failed to get product offers'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ---------------------------------------------------------------------------
# Feature 6: Price Match Negotiation
# ---------------------------------------------------------------------------

class PriceMatchRequestCreateView(APIView):
    """POST /api/price-match/"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            product_id = request.data.get('product_id')
            merchant_id = request.data.get('merchant_id')
            requested_price = request.data.get('requested_price')
            competitor_price = request.data.get('competitor_price')
            competitor_source = request.data.get('competitor_source', '')

            if not all([product_id, merchant_id, requested_price]):
                return Response(
                    {'error': 'product_id, merchant_id and requested_price are required'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                product = Product.objects.get(id=product_id)
            except Product.DoesNotExist:
                return Response({'error': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)

            try:
                merchant = Merchant.objects.get(id=merchant_id)
            except Merchant.DoesNotExist:
                return Response({'error': 'Merchant not found'}, status=status.HTTP_404_NOT_FOUND)

            pmr = PriceMatchRequest.objects.create(
                user=request.user,
                product=product,
                merchant=merchant,
                requested_price=requested_price,
                competitor_price=competitor_price,
                competitor_source=competitor_source,
                expires_at=timezone.now() + timezone.timedelta(days=7),
            )

            # Notify merchant user
            try:
                from apps.core.notification_service import NotificationService
                Notification.objects.create(
                    user=merchant.user,
                    title=f"Price Match Request: {product.name[:50]}",
                    message=(
                        f"{request.user.get_full_name() or request.user.username} "
                        f"has requested a price match to \u20b9{float(requested_price):.0f} "
                        f"for {product.name}."
                    ),
                    notification_type='price_match',
                )
            except Exception as notify_err:
                logger.warning(f"Price match merchant notification failed: {notify_err}")

            return Response(PriceMatchRequestSerializer(pmr).data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error creating price match request: {e}")
            return Response({'error': 'Failed to create price match request'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PriceMatchRequestListView(generics.ListAPIView):
    """GET /api/price-match/"""
    serializer_class = PriceMatchRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PriceMatchRequest.objects.filter(user=self.request.user).select_related('product', 'merchant')


class PriceMatchRequestDetailView(generics.RetrieveAPIView):
    """GET /api/price-match/{id}/"""
    serializer_class = PriceMatchRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PriceMatchRequest.objects.filter(user=self.request.user).select_related('product', 'merchant')


# ---------------------------------------------------------------------------
# Feature 7: Price Alerts & Notification unread count
# ---------------------------------------------------------------------------

class PriceAlertCreateView(APIView):
    """POST /api/alerts/price/"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            product_id = request.data.get('product_id')
            target_price = request.data.get('target_price')

            if not product_id or target_price is None:
                return Response({'error': 'product_id and target_price are required'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                product = Product.objects.get(id=product_id)
            except Product.DoesNotExist:
                return Response({'error': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)

            alert, created = PriceAlert.objects.get_or_create(
                user=request.user,
                product=product,
                defaults={'target_price': target_price, 'is_active': True},
            )
            if not created:
                alert.target_price = target_price
                alert.is_active = True
                alert.save(update_fields=['target_price', 'is_active', 'updated_at'])

            http_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
            return Response(PriceAlertSerializer(alert).data, status=http_status)

        except Exception as e:
            logger.error(f"Error creating price alert: {e}")
            return Response({'error': 'Failed to create price alert'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PriceAlertListView(generics.ListAPIView):
    """GET /api/alerts/price/"""
    serializer_class = PriceAlertSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PriceAlert.objects.filter(user=self.request.user).select_related('product')


class PriceAlertDeleteView(APIView):
    """DELETE /api/alerts/price/{id}/"""
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        try:
            alert = PriceAlert.objects.get(id=pk, user=request.user)
        except PriceAlert.DoesNotExist:
            return Response({'error': 'Price alert not found'}, status=status.HTTP_404_NOT_FOUND)
        alert.delete()
        return Response({'message': 'Price alert deleted'}, status=status.HTTP_200_OK)


class NotificationUnreadCountView(APIView):
    """GET /api/notifications/unread-count/"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        count = request.user.notifications.filter(is_read=False).count()
        return Response({'unread_count': count})
