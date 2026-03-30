"""
AI-powered API Views
Handles requests for ML ranking, basket optimization, price prediction, and smart notifications
"""

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import Q, Count, Avg
import logging

from ..core.models import Product, Cart, CartItem, Notification, UserActivity
from .services_ai import AIService
from .serializers import (
    ProductSearchSerializer, RankedProductSerializer,
    BasketOptimizationSerializer, PricePredictionSerializer,
    BarcodeSearchSerializer, ProductIdentificationSerializer,
    NotificationSerializer, RecommendationSerializer
)

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([AllowAny])
def ranked_products(request):
    """
    Get AI-ranked products
    Query parameters:
    - product_ids: Comma-separated product IDs
    - limit: Maximum number of products to return (default: 10)
    - user_id: User ID for personalization (optional)
    """
    try:
        product_ids = request.GET.get('product_ids', '').split(',')
        product_ids = [int(pid) for pid in product_ids if pid.isdigit()]
        limit = int(request.GET.get('limit', 10))
        
        if not product_ids:
            return Response({
                'success': False,
                'message': 'No product IDs provided',
                'products': []
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Get user for personalization
        user_id = request.GET.get('user_id')
        user = None
        if user_id and user_id.isdigit():
            try:
                user = User.objects.get(id=int(user_id))
            except User.DoesNotExist:
                user = None
        
        # Get ranked products
        ranked_products = AIService.get_ranked_products(user, product_ids, limit)
        
        # Serialize results
        serializer = RankedProductSerializer(ranked_products, many=True)
        
        return Response({
            'success': True,
            'message': f'Retrieved {len(ranked_products)} ranked products',
            'products': serializer.data
        })
        
    except ValueError as e:
        return Response({
            'success': False,
            'message': f'Invalid parameter: {str(e)}',
            'products': []
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Error in ranked_products: {str(e)}")
        return Response({
            'success': False,
            'message': 'Internal server error',
            'products': []
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def basket_optimization(request):
    """
    Optimize user's basket using AI
    GET: Get current optimization status
    POST: Trigger new optimization
    """
    try:
        if request.method == 'GET':
            # Get cached optimization result
            cache_key = f"basket_optimization_{request.user.id}"
            cached_result = cache.get(cache_key)
            
            if cached_result:
                return Response({
                    'success': True,
                    'message': 'Retrieved cached optimization',
                    **cached_result
                })
            else:
                # Perform new optimization
                result = AIService.optimize_user_basket(request.user)
                return Response(result)
        
        elif request.method == 'POST':
            # Force new optimization
            # Clear cache
            cache_key = f"basket_optimization_{request.user.id}"
            cache.delete(cache_key)
            
            # Perform optimization
            result = AIService.optimize_user_basket(request.user)
            
            # Log optimization activity
            UserActivity.objects.create(
                user=request.user,
                activity_type='basket_optimization',
                metadata={
                    'total_savings': result.get('total_savings', 0),
                    'savings_percentage': result.get('savings_percentage', 0),
                    'strategy': result.get('optimization_strategy', 'balanced')
                }
            )
            
            return Response(result)
            
    except Exception as e:
        logger.error(f"Error in basket_optimization: {str(e)}")
        return Response({
            'success': False,
            'message': 'Basket optimization failed',
            'current_total': 0,
            'optimized_total': 0,
            'total_savings': 0,
            'recommendations': []
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def price_prediction(request):
    """
    Predict price trends for products
    GET: Get predictions for product IDs
    POST: Get predictions with custom parameters
    """
    try:
        if request.method == 'GET':
            product_ids = request.GET.get('product_ids', '').split(',')
            product_ids = [int(pid) for pid in product_ids if pid.isdigit()]
            days_ahead = int(request.GET.get('days_ahead', 7))
            
            if not product_ids:
                return Response({
                    'success': False,
                    'message': 'No product IDs provided',
                    'predictions': {}
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get user for personalization
            user = request.user if request.user.is_authenticated else None
            
            # Get predictions
            result = AIService.predict_prices(user, product_ids, days_ahead)
            
            return Response(result)
            
        elif request.method == 'POST':
            data = request.data
            product_ids = data.get('product_ids', [])
            days_ahead = int(data.get('days_ahead', 7))
            
            if not product_ids:
                return Response({
                    'success': False,
                    'message': 'No product IDs provided',
                    'predictions': {}
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get user for personalization
            user = request.user if request.user.is_authenticated else None
            
            # Get predictions
            result = AIService.predict_prices(user, product_ids, days_ahead)
            
            # Log prediction activity
            if user:
                UserActivity.objects.create(
                    user=user,
                    activity_type='price_prediction',
                    metadata={
                        'product_ids': product_ids,
                        'days_ahead': days_ahead,
                        'predictions_count': len(result.get('predictions', {}))
                    }
                )
            
            return Response(result)
            
    except ValueError as e:
        return Response({
            'success': False,
            'message': f'Invalid parameter: {str(e)}',
            'predictions': {}
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Error in price_prediction: {str(e)}")
        return Response({
            'success': False,
            'message': 'Price prediction failed',
            'predictions': {}
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def barcode_search(request):
    """
    Search products by barcode
    GET: Simple barcode search
    POST: Advanced barcode search with options
    """
    try:
        if request.method == 'GET':
            barcode_value = request.GET.get('barcode')
            
            if not barcode_value:
                return Response({
                    'success': False,
                    'message': 'No barcode provided',
                    'products': []
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get user for personalization
            user = request.user if request.user.is_authenticated else None
            
            # Search barcode
            result = AIService.scan_product_barcode(user, barcode_value)
            
            # Log search activity
            if user:
                UserActivity.objects.create(
                    user=user,
                    activity_type='barcode_search',
                    metadata={
                        'barcode': barcode_value,
                        'found': result.get('found', False),
                        'products_count': len(result.get('products', []))
                    }
                )
            
            return Response(result)
            
        elif request.method == 'POST':
            data = request.data
            barcode_value = data.get('barcode')
            
            if not barcode_value:
                return Response({
                    'success': False,
                    'message': 'No barcode provided',
                    'products': []
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get user for personalization
            user = request.user if request.user.is_authenticated else None
            
            # Search barcode with additional options
            result = AIService.scan_product_barcode(user, barcode_value)
            
            # Add additional options from POST data
            if data.get('include_similar', False):
                # Add similar products logic here
                pass
            
            # Log search activity
            if user:
                UserActivity.objects.create(
                    user=user,
                    activity_type='barcode_search',
                    metadata={
                        'barcode': barcode_value,
                        'found': result.get('found', False),
                        'products_count': len(result.get('products', [])),
                        'advanced_search': True
                    }
                )
            
            return Response(result)
            
    except Exception as e:
        logger.error(f"Error in barcode_search: {str(e)}")
        return Response({
            'success': False,
            'message': 'Barcode search failed',
            'products': []
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
@permission_classes([AllowAny])
@parser_classes([MultiPartParser, FormParser])
def product_identification(request):
    """
    Identify product from image using AI
    POST: Upload image for product identification
    """
    try:
        if 'image' not in request.FILES:
            return Response({
                'success': False,
                'message': 'No image provided',
                'products': []
            }, status=status.HTTP_400_BAD_REQUEST)
        
        image_file = request.FILES['image']
        image_data = image_file.read()
        
        # Get user for personalization
        user = request.user if request.user.is_authenticated else None
        
        # Identify product from image
        result = AIService.identify_product_from_image(user, image_data)
        
        # Log identification activity
        if user:
            UserActivity.objects.create(
                user=user,
                activity_type='image_search',
                metadata={
                    'image_name': image_file.name,
                    'image_size': len(image_data),
                    'found': result.get('found', False),
                    'products_count': len(result.get('products', []))
                }
            )
        
        return Response(result)
        
    except Exception as e:
        logger.error(f"Error in product_identification: {str(e)}")
        return Response({
            'success': False,
            'message': 'Product identification failed',
            'products': []
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def smart_notifications(request):
    """
    Get smart notifications for user
    GET: Get notifications
    POST: Mark notifications as read
    """
    try:
        if request.method == 'GET':
            limit = int(request.GET.get('limit', 10))
            unread_only = request.GET.get('unread_only', 'false').lower() == 'true'
            
            # Get smart notifications
            result = AIService.get_smart_notifications(request.user, limit)
            
            if unread_only:
                # Filter only unread notifications
                result['notifications'] = [
                    n for n in result['notifications'] 
                    if not n.get('is_read', True)
                ]
            
            return Response(result)
            
        elif request.method == 'POST':
            data = request.data
            notification_ids = data.get('notification_ids', [])
            
            if not notification_ids:
                return Response({
                    'success': False,
                    'message': 'No notification IDs provided'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Mark notifications as read
            updated_count = Notification.objects.filter(
                id__in=notification_ids,
                user=request.user,
                is_read=False
            ).update(is_read=True)
            
            return Response({
                'success': True,
                'message': f'Marked {updated_count} notifications as read',
                'updated_count': updated_count
            })
            
    except ValueError as e:
        return Response({
            'success': False,
            'message': f'Invalid parameter: {str(e)}'
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Error in smart_notifications: {str(e)}")
        return Response({
            'success': False,
            'message': 'Failed to retrieve notifications'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([AllowAny])
def personalized_recommendations(request):
    """
    Get personalized product recommendations using AI
    Query parameters:
    - limit: Maximum number of recommendations (default: 10)
    - user_id: User ID for personalization (optional)
    - category: Filter by category (optional)
    """
    try:
        limit = int(request.GET.get('limit', 10))
        category_filter = request.GET.get('category')
        
        # Get user for personalization
        user = None
        if request.user.is_authenticated:
            user = request.user
        elif 'user_id' in request.GET and request.GET['user_id'].isdigit():
            try:
                user = User.objects.get(id=int(request.GET['user_id']))
            except User.DoesNotExist:
                user = None
        
        # Get personalized recommendations
        result = AIService.get_personalized_recommendations(user, limit)
        
        # Apply category filter if provided
        if category_filter and result['success']:
            result['recommendations'] = [
                r for r in result['recommendations']
                if r['category'].lower() == category_filter.lower()
            ]
            result['message'] = f"Found {len(result['recommendations'])} recommendations in {category_filter}"
        
        # Log recommendation activity
        if user:
            UserActivity.objects.create(
                user=user,
                activity_type='recommendation_view',
                metadata={
                    'recommendations_count': len(result.get('recommendations', [])),
                    'category_filter': category_filter,
                    'limit': limit
                }
            )
        
        return Response(result)
        
    except ValueError as e:
        return Response({
            'success': False,
            'message': f'Invalid parameter: {str(e)}',
            'recommendations': []
        }, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Error in personalized_recommendations: {str(e)}")
        return Response({
            'success': False,
            'message': 'Failed to get recommendations',
            'recommendations': []
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ai_insights(request):
    """
    Get AI-powered insights for user
    Returns personalized insights and trends
    """
    try:
        user = request.user
        
        # Get user's recent activity
        recent_activity = UserActivity.objects.filter(
            user=user
        ).order_by('-created_at')[:50]
        
        # Get user's cart items
        cart_items = CartItem.objects.filter(
            cart__user=user
        ).select_related('product')
        
        # Get user's notifications
        notifications = Notification.objects.filter(
            user=user,
            is_read=False
        ).order_by('-created_at')[:5]
        
        # Generate insights
        insights = {
            'search_trends': _analyze_search_trends(recent_activity),
            'price_savings': _calculate_potential_savings(cart_items),
            'recommendation_accuracy': _calculate_recommendation_accuracy(user),
            'engagement_score': _calculate_engagement_score(recent_activity),
            'next_actions': _generate_next_actions(recent_activity, cart_items, notifications)
        }
        
        return Response({
            'success': True,
            'message': 'Generated AI insights',
            'insights': insights
        })
        
    except Exception as e:
        logger.error(f"Error in ai_insights: {str(e)}")
        return Response({
            'success': False,
            'message': 'Failed to generate insights',
            'insights': {}
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# Helper functions for AI insights
def _analyze_search_trends(activities):
    """Analyze user's search trends"""
    search_activities = activities.filter(activity_type='search')
    
    if not search_activities.exists():
        return {
            'most_searched_categories': [],
            'search_frequency': 0,
            'trending_up': []
        }
    
    # Extract search data
    search_data = []
    for activity in search_activities:
        metadata = activity.metadata or {}
        if 'query' in metadata:
            search_data.append({
                'query': metadata['query'],
                'timestamp': activity.created_at
            })
    
    # Analyze trends (simplified)
    return {
        'most_searched_categories': ['Electronics', 'Clothing', 'Home'],  # Placeholder
        'search_frequency': len(search_data),
        'trending_up': ['Smartphones', 'Laptops']  # Placeholder
    }

def _calculate_potential_savings(cart_items):
    """Calculate potential savings from cart optimization"""
    if not cart_items.exists():
        return {
            'current_total': 0,
            'potential_savings': 0,
            'optimization_opportunities': 0
        }
    
    current_total = sum(
        float(item.product.amazon_price or 0) * item.quantity 
        for item in cart_items
    )
    
    # Get AI optimization
    from .services_ai import AIService
    optimization = AIService.optimize_user_basket(cart_items.first().cart.user)
    
    return {
        'current_total': current_total,
        'potential_savings': optimization.get('total_savings', 0),
        'optimization_opportunities': len(optimization.get('recommendations', []))
    }

def _calculate_recommendation_accuracy(user):
    """Calculate how accurate recommendations have been"""
    # This would track if user interacts with recommendations
    # Simplified implementation
    return {
        'accuracy_score': 0.75,  # Placeholder
        'total_recommendations': 24,
        'accepted_recommendations': 18
    }

def _calculate_engagement_score(activities):
    """Calculate user engagement score"""
    if not activities.exists():
        return 0.0
    
    # Simple engagement calculation based on activity frequency
    activity_types = activities.values_list('activity_type', flat=True).distinct()
    engagement_score = min(len(activity_types) / 5.0, 1.0)  # Normalize to 0-1
    
    return engagement_score

def _generate_next_actions(activities, cart_items, notifications):
    """Generate recommended next actions for user"""
    actions = []
    
    # Cart optimization action
    if cart_items.exists() and cart_items.count() > 1:
        actions.append({
            'type': 'optimize_cart',
            'title': 'Optimize Your Cart',
            'description': 'Save money by optimizing your basket',
            'priority': 'high'
        })
    
    # Price drop alerts
    unread_notifications = notifications.filter(notification_type='price_drop')
    if unread_notifications.exists():
        actions.append({
            'type': 'check_price_drops',
            'title': 'Price Drops Detected',
            'description': f'{unread_notifications.count()} products have price drops',
            'priority': 'medium'
        })
    
    # Continue shopping
    if not cart_items.exists():
        actions.append({
            'type': 'continue_shopping',
            'title': 'Continue Shopping',
            'description': 'Browse personalized recommendations',
            'priority': 'low'
        })
    
    return actions
