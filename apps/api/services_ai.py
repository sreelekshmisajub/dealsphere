"""
AI-powered API Services
Connects Django API endpoints with AI integration
"""

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import Q, Count, Avg, Min, Max
from decimal import Decimal
import logging

from ..core.models import Product, Offer, Merchant, Cart, CartItem, Notification, UserActivity, PriceHistory
from ..ai_engine.integrations import ai_integration

logger = logging.getLogger(__name__)

class AIService:
    """AI-powered services for API endpoints"""
    
    @staticmethod
    def search_products_with_ai(user, query, filters=None, sort_by='relevance'):
        """
        Search products with AI ranking
        Returns ranked products with ML scores
        """
        try:
            # Base product query
            products_query = Product.objects.select_related('category', 'brand')
            
            # Apply search filters
            if query:
                products_query = products_query.filter(
                    Q(name__icontains=query) |
                    Q(category__name__icontains=query) |
                    Q(brand__name__icontains=query) |
                    Q(description__icontains=query)
                )
            
            # Apply additional filters
            if filters:
                if filters.get('category'):
                    products_query = products_query.filter(category__name__in=filters['category'])
                
                if filters.get('min_price'):
                    products_query = products_query.filter(
                        Q(amazon_price__gte=filters['min_price']) |
                        Q(offer__price__gte=filters['min_price'])
                    )
                
                if filters.get('max_price'):
                    products_query = products_query.filter(
                        Q(amazon_price__lte=filters['max_price']) |
                        Q(offer__price__lte=filters['max_price'])
                    )
                
                if filters.get('min_rating'):
                    products_query = products_query.filter(rating__gte=filters['min_rating'])
                
                if filters.get('verified_only'):
                    products_query = products_query.filter(offer__merchant__verified=True)
            
            # Get products
            products = products_query.distinct()
            
            # Apply AI ranking
            if user and user.is_authenticated:
                user_location = getattr(user, 'location', None)
                ranked_products = ai_integration.rank_products(
                    user=user,
                    products=products,
                    search_query=query,
                    user_location=user_location
                )
            else:
                # For anonymous users, use basic ranking
                ranked_products = list(products)
                # Sort by relevance (basic implementation)
                if query:
                    ranked_products.sort(key=lambda x: (
                        query.lower() in x.name.lower() * -1,
                        x.rating or 0
                    ), reverse=True)
                else:
                    ranked_products.sort(key=lambda x: x.rating or 0, reverse=True)
            
            # Apply secondary sorting
            if sort_by == 'price_low':
                ranked_products.sort(key=lambda x: AIService._get_product_price(x))
            elif sort_by == 'price_high':
                ranked_products.sort(key=lambda x: AIService._get_product_price(x), reverse=True)
            elif sort_by == 'rating':
                ranked_products.sort(key=lambda x: x.rating or 0, reverse=True)
            
            return ranked_products
            
        except Exception as e:
            logger.error(f"Error in AI product search: {str(e)}")
            return Product.objects.none()
    
    @staticmethod
    def get_ranked_products(user, product_ids, limit=10):
        """
        Get AI-ranked products for given IDs
        """
        try:
            products = Product.objects.filter(id__in=product_ids).select_related('category', 'brand')
            
            if user and user.is_authenticated:
                ranked_products = ai_integration.rank_products(
                    user=user,
                    products=products,
                    search_query=None
                )
            else:
                ranked_products = list(products)
                ranked_products.sort(key=lambda x: x.rating or 0, reverse=True)
            
            return ranked_products[:limit]
            
        except Exception as e:
            logger.error(f"Error getting ranked products: {str(e)}")
            return Product.objects.filter(id__in=product_ids)[:limit]
    
    @staticmethod
    def optimize_user_basket(user):
        """
        Optimize user's basket using AI
        Returns optimization results with real savings calculations
        """
        try:
            cart_items = CartItem.objects.filter(cart__user=user).select_related('product')
            
            if not cart_items.exists():
                return {
                    'success': False,
                    'message': 'Your cart is empty',
                    'current_total': 0,
                    'optimized_total': 0,
                    'total_savings': 0,
                    'recommendations': []
                }
            
            # Get AI optimization
            optimization_result = ai_integration.optimize_basket(user, cart_items)
            
            if 'error' in optimization_result:
                return {
                    'success': False,
                    'message': optimization_result['error'],
                    'current_total': 0,
                    'optimized_total': 0,
                    'total_savings': 0,
                    'recommendations': []
                }
            
            # Format results for API response
            result = {
                'success': True,
                'message': f'Optimized! You can save ₹{optimization_result["total_savings"]:.2f}',
                'current_total': float(optimization_result['current_total']),
                'optimized_total': float(optimization_result['optimized_total']),
                'total_savings': float(optimization_result['total_savings']),
                'savings_percentage': float(optimization_result['savings_percentage']),
                'recommendations': optimization_result['recommendations'],
                'optimization_strategy': optimization_result['optimization_strategy'],
                'split_purchase': optimization_result.get('split_purchase', {}),
                'single_store': optimization_result.get('single_store', {})
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error optimizing basket: {str(e)}")
            return {
                'success': False,
                'message': 'Basket optimization temporarily unavailable',
                'current_total': 0,
                'optimized_total': 0,
                'total_savings': 0,
                'recommendations': []
            }
    
    @staticmethod
    def predict_prices(user, product_ids, days_ahead=7):
        """
        Predict prices for products using AI
        Returns predictions with confidence scores
        """
        try:
            predictions = ai_integration.predict_price_trends(product_ids, days_ahead)
            
            # Format predictions for API response
            formatted_predictions = {}
            for product_id, prediction in predictions.items():
                formatted_predictions[product_id] = {
                    'product_id': product_id,
                    'current_price': prediction['current_price'],
                    'predicted_price': prediction['predicted_price'],
                    'trend': prediction['trend'],
                    'confidence': prediction['confidence'],
                    'days_ahead': prediction['days_ahead'],
                    'recommendation': prediction['recommendation'],
                    'potential_savings': prediction.get('potential_savings', 0),
                    'best_buy_date': prediction.get('best_buy_date'),
                    'price_drop_probability': prediction.get('price_drop_probability', 0)
                }
            
            return {
                'success': True,
                'predictions': formatted_predictions,
                'message': f'Price predictions for {len(formatted_predictions)} products'
            }
            
        except Exception as e:
            logger.error(f"Error predicting prices: {str(e)}")
            return {
                'success': False,
                'message': 'Price prediction temporarily unavailable',
                'predictions': {}
            }
    
    @staticmethod
    def scan_product_barcode(user, barcode_value):
        """
        Scan barcode and find products
        Returns matching products with real data
        """
        try:
            result = ai_integration.scan_barcode(barcode_value)
            
            if result['found']:
                # Format products for API response
                formatted_products = []
                for product_data in result['products']:
                    product = product_data['product']
                    best_offer = product_data['best_offer']
                    
                    formatted_products.append({
                        'id': product.id,
                        'name': product.name,
                        'category': product.category.name if product.category else 'General',
                        'brand': product.brand.name if product.brand else 'Unknown',
                        'image_url': product.image_url,
                        'current_price': float(AIService._get_product_price(product)),
                        'best_offer': {
                            'price': float(best_offer.price) if best_offer else None,
                            'merchant': best_offer.merchant.shop_name if best_offer else None,
                            'delivery_time': best_offer.delivery_time_hours if best_offer else None
                        } if best_offer else None,
                        'match_confidence': product_data['match_confidence'],
                        'match_type': product_data['match_type'],
                        'rating': float(product.rating or 0),
                        'reviews_count': int(product.reviews_count or 0)
                    })
                
                return {
                    'success': True,
                    'found': True,
                    'products': formatted_products,
                    'barcode_info': result['barcode_info'],
                    'message': f'Found {len(formatted_products)} matching products'
                }
            else:
                return {
                    'success': True,
                    'found': False,
                    'products': [],
                    'barcode_value': barcode_value,
                    'suggestions': result.get('suggestions', []),
                    'message': 'No products found for this barcode'
                }
                
        except Exception as e:
            logger.error(f"Error scanning barcode: {str(e)}")
            return {
                'success': False,
                'found': False,
                'products': [],
                'message': 'Barcode scanning temporarily unavailable'
            }
    
    @staticmethod
    def identify_product_from_image(user, image_data):
        """
        Identify product from image using AI
        Returns matching products with confidence scores
        """
        try:
            result = ai_integration.identify_product_from_image(image_data)
            
            if result['found']:
                # Format products for API response
                formatted_products = []
                for product_data in result['products']:
                    product = product_data['product']
                    best_offer = product_data['best_offer']
                    
                    formatted_products.append({
                        'id': product.id,
                        'name': product.name,
                        'category': product.category.name if product.category else 'General',
                        'brand': product.brand.name if product.brand else 'Unknown',
                        'image_url': product.image_url,
                        'current_price': float(AIService._get_product_price(product)),
                        'best_offer': {
                            'price': float(best_offer.price) if best_offer else None,
                            'merchant': best_offer.merchant.shop_name if best_offer else None,
                            'delivery_time': best_offer.delivery_time_hours if best_offer else None
                        } if best_offer else None,
                        'match_score': product_data['match_score'],
                        'identification_confidence': product_data['identification_confidence'],
                        'rating': float(product.rating or 0),
                        'reviews_count': int(product.reviews_count or 0)
                    })
                
                return {
                    'success': True,
                    'found': True,
                    'products': formatted_products,
                    'identification_info': result['identification_info'],
                    'message': f'Identified {len(formatted_products)} matching products'
                }
            else:
                return {
                    'success': True,
                    'found': False,
                    'products': [],
                    'identification_info': result.get('identification_info', {}),
                    'suggestions': result.get('suggestions', []),
                    'message': 'Could not identify product from image'
                }
                
        except Exception as e:
            logger.error(f"Error identifying product from image: {str(e)}")
            return {
                'success': False,
                'found': False,
                'products': [],
                'message': 'Image identification temporarily unavailable'
            }
    
    @staticmethod
    def get_smart_notifications(user, limit=10):
        """
        Get smart notifications for user
        Returns personalized notifications based on AI insights
        """
        try:
            if not user or not user.is_authenticated:
                return {
                    'success': True,
                    'notifications': [],
                    'message': 'User not authenticated'
                }
            
            # Generate smart notifications
            smart_notifications = ai_integration.generate_smart_notifications(user)
            
            # Get existing unread notifications
            existing_notifications = Notification.objects.filter(
                user=user,
                is_read=False
            ).order_by('-created_at')[:limit - len(smart_notifications)]
            
            # Format all notifications
            formatted_notifications = []
            
            # Add AI-generated notifications
            for notification in smart_notifications:
                formatted_notifications.append({
                    'id': None,  # New notification, not saved yet
                    'title': notification['title'],
                    'message': notification['message'],
                    'type': notification['type'],
                    'priority': notification['priority'],
                    'is_read': False,
                    'created_at': None,  # New notification
                    'product': {
                        'id': notification['product'].id,
                        'name': notification['product'].name,
                        'image_url': notification['product'].image_url
                    } if notification.get('product') else None,
                    'data': notification.get('data', {})
                })
            
            # Add existing notifications
            for notification in existing_notifications:
                formatted_notifications.append({
                    'id': notification.id,
                    'title': notification.title,
                    'message': notification.message,
                    'type': notification.notification_type,
                    'priority': notification.priority,
                    'is_read': notification.is_read,
                    'created_at': notification.created_at.isoformat(),
                    'product': {
                        'id': notification.product.id,
                        'name': notification.product.name,
                        'image_url': notification.product.image_url
                    } if notification.product else None,
                    'data': notification.metadata or {}
                })
            
            # Sort by priority and creation date
            priority_order = {'high': 3, 'medium': 2, 'low': 1}
            formatted_notifications.sort(key=lambda x: (
                priority_order.get(x['priority'], 0),
                x['created_at'] or ''
            ), reverse=True)
            
            return {
                'success': True,
                'notifications': formatted_notifications[:limit],
                'message': f'Found {len(formatted_notifications)} notifications'
            }
            
        except Exception as e:
            logger.error(f"Error getting smart notifications: {str(e)}")
            return {
                'success': False,
                'notifications': [],
                'message': 'Notifications temporarily unavailable'
            }
    
    @staticmethod
    def get_personalized_recommendations(user, limit=10):
        """
        Get personalized product recommendations using AI
        Returns products based on user preferences and behavior
        """
        try:
            if not user or not user.is_authenticated:
                # Return popular products for anonymous users
                products = Product.objects.select_related('category', 'brand').order_by('-rating', '-reviews_count')[:limit]
            else:
                # Get AI-powered recommendations
                watched_products = ai_integration._get_watched_products(user)
                preferences = ai_integration._get_user_preferences(user)
                
                # Get products from preferred categories
                preferred_categories = [cat[0] for cat in preferences['preferred_categories'][:3]]
                
                products_query = Product.objects.select_related('category', 'brand')
                
                if preferred_categories:
                    products_query = products_query.filter(category__name__in=preferred_categories)
                
                # Exclude products user has already viewed
                viewed_product_ids = UserActivity.objects.filter(
                    user=user,
                    activity_type='product_view'
                ).values_list('product__id', flat=True)
                
                products_query = products_query.exclude(id__in=viewed_product_ids)
                
                products = products_query.order_by('-rating', '-reviews_count')[:limit]
            
            # Format recommendations
            recommendations = []
            for product in products:
                best_offer = AIService._get_best_offer_for_product(product)
                
                recommendations.append({
                    'id': product.id,
                    'name': product.name,
                    'category': product.category.name if product.category else 'General',
                    'brand': product.brand.name if product.brand else 'Unknown',
                    'image_url': product.image_url,
                    'current_price': float(AIService._get_product_price(product)),
                    'best_offer': {
                        'price': float(best_offer.price) if best_offer else None,
                        'merchant': best_offer.merchant.shop_name if best_offer else None,
                        'delivery_time': best_offer.delivery_time_hours if best_offer else None,
                        'discount_percentage': best_offer.discount_percentage if best_offer else None
                    } if best_offer else None,
                    'rating': float(product.rating or 0),
                    'reviews_count': int(product.reviews_count or 0),
                    'recommendation_score': AIService._calculate_recommendation_score(product, user) if user and user.is_authenticated else 0.5
                })
            
            # Sort by recommendation score for authenticated users
            if user and user.is_authenticated:
                recommendations.sort(key=lambda x: x['recommendation_score'], reverse=True)
            
            return {
                'success': True,
                'recommendations': recommendations,
                'message': f'Found {len(recommendations)} personalized recommendations'
            }
            
        except Exception as e:
            logger.error(f"Error getting recommendations: {str(e)}")
            return {
                'success': False,
                'recommendations': [],
                'message': 'Recommendations temporarily unavailable'
            }
    
    # Helper methods
    @staticmethod
    def _get_product_price(product):
        """Get the best price for a product"""
        best_offer = AIService._get_best_offer_for_product(product)
        if best_offer:
            return best_offer.price
        return product.amazon_price or 0
    
    @staticmethod
    def _get_best_offer_for_product(product):
        """Get the best offer for a product"""
        return Offer.objects.filter(product=product).order_by('price').first()
    
    @staticmethod
    def _calculate_recommendation_score(product, user):
        """Calculate recommendation score for a product and user"""
        try:
            # Get user preferences
            preferences = ai_integration._get_user_preferences(user)
            score = 0.5  # Base score
            
            # Category preference boost
            if product.category:
                for cat, count in preferences['preferred_categories']:
                    if product.category.name == cat:
                        score += 0.1 * (count / 10)
            
            # Brand preference boost
            if product.brand:
                for brand, count in preferences['preferred_brands']:
                    if product.brand.name == brand:
                        score += 0.1 * (count / 10)
            
            # Price preference alignment
            product_price = float(AIService._get_product_price(product))
            if abs(product_price - preferences['avg_price_range']) < preferences['avg_price_range'] * 0.3:
                score += 0.2
            
            # Rating boost
            if product.rating:
                score += min(product.rating / 5.0 * 0.2, 0.2)
            
            return min(score, 1.0)
            
        except Exception:
            return 0.5
