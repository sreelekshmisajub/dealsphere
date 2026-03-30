"""
AI-powered User Services
Integrates AI features with user-specific operations
"""

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import Q, Count, Avg, Sum
from decimal import Decimal
import logging

from ..core.models import Product, Cart, CartItem, Notification, UserActivity, PriceHistory
from ..ai_engine.integrations import ai_integration

logger = logging.getLogger(__name__)

class UserAIService:
    """AI services for user-specific operations"""
    
    @staticmethod
    def get_personalized_search_results(user, query, filters=None, sort_by='relevance'):
        """
        Get personalized search results for user
        Uses AI ranking based on user preferences and activity
        """
        try:
            from ..api.services_ai import AIService
            
            # Get AI-ranked search results
            ranked_products = AIService.search_products_with_ai(
                user=user,
                query=query,
                filters=filters,
                sort_by=sort_by
            )
            
            # Log search activity
            if user and user.is_authenticated:
                UserActivity.objects.create(
                    user=user,
                    activity_type='search',
                    metadata={
                        'query': query,
                        'filters': filters or {},
                        'results_count': len(ranked_products),
                        'sort_by': sort_by
                    }
                )
            
            return ranked_products
            
        except Exception as e:
            logger.error(f"Error getting personalized search results: {str(e)}")
            return Product.objects.none()
    
    @staticmethod
    def get_smart_cart_recommendations(user):
        """
        Get smart recommendations for user's cart
        Suggests additional products and optimizations
        """
        try:
            cart_items = CartItem.objects.filter(
                cart__user=user
            ).select_related('product', 'product__category')
            
            if not cart_items.exists():
                return {
                    'recommendations': [],
                    'optimization_suggestions': [],
                    'frequently_bought_together': []
                }
            
            recommendations = []
            
            # Get products frequently bought together
            cart_product_ids = [item.product.id for item in cart_items]
            frequently_bought = UserActivity.objects.filter(
                activity_type='add_to_cart',
                metadata__product_id__in=cart_product_ids
            ).values('metadata__related_product_id').annotate(
                count=Count('id')
            ).order_by('-count')[:5]
            
            # Convert to product recommendations
            for item in frequently_bought:
                related_product_id = item['metadata__related_product_id']
                if related_product_id and related_product_id not in cart_product_ids:
                    try:
                        product = Product.objects.get(id=related_product_id)
                        recommendations.append({
                            'product': product,
                            'reason': 'frequently_bought_together',
                            'confidence': item['count'] / 10.0,  # Normalized confidence
                            'count': item['count']
                        })
                    except Product.DoesNotExist:
                        continue
            
            # Get AI basket optimization suggestions
            from ..api.services_ai import AIService
            optimization = AIService.optimize_user_basket(user)
            
            optimization_suggestions = []
            if optimization.get('success') and optimization.get('recommendations'):
                optimization_suggestions = optimization['recommendations']
            
            return {
                'recommendations': recommendations,
                'optimization_suggestions': optimization_suggestions,
                'frequently_bought_together': [r['product'] for r in recommendations[:3]]
            }
            
        except Exception as e:
            logger.error(f"Error getting smart cart recommendations: {str(e)}")
            return {
                'recommendations': [],
                'optimization_suggestions': [],
                'frequently_bought_together': []
            }
    
    @staticmethod
    def get_price_drop_alerts(user):
        """
        Get price drop alerts for user's watched products
        """
        try:
            # Get user's watched products (based on activity)
            watched_product_ids = UserActivity.objects.filter(
                user=user,
                activity_type__in=['product_view', 'add_to_cart', 'search']
            ).values_list('product__id', flat=True).distinct()
            
            if not watched_product_ids:
                return []
            
            # Get price predictions for watched products
            predictions = ai_integration.predict_price_trends(list(watched_product_ids), days_ahead=7)
            
            price_drop_alerts = []
            for product_id, prediction in predictions.items():
                if prediction['trend'] == 'dropping' and prediction['confidence'] > 0.6:
                    try:
                        product = Product.objects.get(id=product_id)
                        price_drop_alerts.append({
                            'product': product,
                            'current_price': prediction['current_price'],
                            'predicted_price': prediction['predicted_price'],
                            'potential_savings': prediction.get('potential_savings', 0),
                            'confidence': prediction['confidence'],
                            'days_ahead': prediction['days_ahead'],
                            'price_drop_probability': prediction.get('price_drop_probability', 0)
                        })
                    except Product.DoesNotExist:
                        continue
            
            # Sort by potential savings
            price_drop_alerts.sort(key=lambda x: x['potential_savings'], reverse=True)
            
            return price_drop_alerts
            
        except Exception as e:
            logger.error(f"Error getting price drop alerts: {str(e)}")
            return []
    
    @staticmethod
    def get_personalized_deals(user, limit=10):
        """
        Get personalized deals for user
        Based on user preferences and AI insights
        """
        try:
            # Get user preferences
            user_preferences = ai_integration._get_user_preferences(user)
            preferred_categories = [cat[0] for cat in user_preferences['preferred_categories'][:3]]
            
            # Get deals in preferred categories
            deals_query = Product.objects.filter(
                offer__discount_percentage__gte=10  # At least 10% discount
            ).select_related('category', 'brand')
            
            if preferred_categories:
                deals_query = deals_query.filter(category__name__in=preferred_categories)
            
            # Exclude products user has already viewed
            viewed_product_ids = UserActivity.objects.filter(
                user=user,
                activity_type='product_view'
            ).values_list('product__id', flat=True)
            
            deals_query = deals_query.exclude(id__in=viewed_product_ids)
            
            # Get deals and rank them
            deals = deals_query.distinct()[:limit * 2]  # Get more to rank
            
            # Rank deals based on user preferences
            ranked_deals = []
            for deal in deals:
                best_offer = ai_integration._get_best_offer(deal)
                
                # Calculate personalization score
                personalization_score = 0.5  # Base score
                
                # Category preference
                if deal.category and deal.category.name in preferred_categories:
                    cat_index = preferred_categories.index(deal.category.name)
                    personalization_score += (3 - cat_index) * 0.1
                
                # Brand preference
                preferred_brands = [brand[0] for brand in user_preferences['preferred_brands'][:3]]
                if deal.brand and deal.brand.name in preferred_brands:
                    personalization_score += 0.2
                
                # Price preference alignment
                deal_price = float(best_offer.price) if best_offer else float(deal.amazon_price or 0)
                if abs(deal_price - user_preferences['avg_price_range']) < user_preferences['avg_price_range'] * 0.5:
                    personalization_score += 0.1
                
                ranked_deals.append({
                    'product': deal,
                    'best_offer': best_offer,
                    'personalization_score': personalization_score,
                    'discount_percentage': best_offer.discount_percentage if best_offer else 0
                })
            
            # Sort by personalization score and discount
            ranked_deals.sort(key=lambda x: (x['personalization_score'], x['discount_percentage']), reverse=True)
            
            return ranked_deals[:limit]
            
        except Exception as e:
            logger.error(f"Error getting personalized deals: {str(e)}")
            return []
    
    @staticmethod
    def track_user_interaction(user, product, interaction_type, metadata=None):
        """
        Track user interaction with products for AI learning
        """
        try:
            if not user or not user.is_authenticated:
                return
            
            # Create activity record
            UserActivity.objects.create(
                user=user,
                product=product,
                activity_type=interaction_type,
                metadata=metadata or {}
            )
            
            # Update user preferences in cache
            cache_key = f"user_preferences_{user.id}"
            cache.delete(cache_key)  # Force refresh on next access
            
            # Update product popularity
            product_popularity_key = f"product_popularity_{product.id}"
            current_popularity = cache.get(product_popularity_key, 0)
            cache.set(product_popularity_key, current_popularity + 1, timeout=3600)  # 1 hour
            
        except Exception as e:
            logger.error(f"Error tracking user interaction: {str(e)}")
    
    @staticmethod
    def get_smart_suggestions(user, context='general'):
        """
        Get smart suggestions based on user context
        """
        try:
            suggestions = []
            
            if context == 'search':
                # Search suggestions based on user history
                recent_searches = UserActivity.objects.filter(
                    user=user,
                    activity_type='search'
                ).values_list('metadata__query', flat=True).distinct()[:10]
                
                for search in recent_searches:
                    if search:
                        suggestions.append({
                            'type': 'search_suggestion',
                            'text': search,
                            'reason': 'recent_search'
                        })
            
            elif context == 'cart':
                # Cart suggestions
                cart_recommendations = UserAIService.get_smart_cart_recommendations(user)
                for rec in cart_recommendations['frequently_bought_together']:
                    suggestions.append({
                        'type': 'product_suggestion',
                        'product': rec,
                        'reason': 'frequently_bought_together'
                    })
            
            elif context == 'homepage':
                # Homepage personalized suggestions
                price_drops = UserAIService.get_price_drop_alerts(user)
                for drop in price_drops[:3]:
                    suggestions.append({
                        'type': 'price_drop_alert',
                        'product': drop['product'],
                        'potential_savings': drop['potential_savings'],
                        'reason': 'price_dropping'
                    })
                
                # Add personalized deals
                deals = UserAIService.get_personalized_deals(user, limit=5)
                for deal in deals:
                    suggestions.append({
                        'type': 'personalized_deal',
                        'product': deal['product'],
                        'discount_percentage': deal['discount_percentage'],
                        'reason': 'personalized_for_you'
                    })
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error getting smart suggestions: {str(e)}")
            return []
    
    @staticmethod
    def get_user_ai_profile(user):
        """
        Get user's AI profile based on behavior and preferences
        """
        try:
            # Get user activity summary
            activities = UserActivity.objects.filter(user=user)
            
            # Calculate metrics
            total_searches = activities.filter(activity_type='search').count()
            total_views = activities.filter(activity_type='product_view').count()
            total_cart_adds = activities.filter(activity_type='add_to_cart').count()
            
            # Get preferences
            preferences = ai_integration._get_user_preferences(user)
            
            # Calculate engagement score
            activity_types = activities.values_list('activity_type', flat=True).distinct()
            engagement_score = min(len(activity_types) / 5.0, 1.0)
            
            # Calculate price sensitivity
            price_activities = activities.filter(
                metadata__price__isnull=False
            ).values_list('metadata__price', flat=True)
            
            if price_activities:
                avg_price_viewed = sum(price_activities) / len(price_activities)
                price_sensitivity = 'low' if avg_price_viewed > 5000 else 'high' if avg_price_viewed < 1000 else 'medium'
            else:
                price_sensitivity = 'medium'
            
            return {
                'user_id': user.id,
                'engagement_score': engagement_score,
                'total_interactions': activities.count(),
                'search_frequency': total_searches,
                'view_to_cart_ratio': total_cart_adds / max(total_views, 1),
                'price_sensitivity': price_sensitivity,
                'preferred_categories': preferences['preferred_categories'],
                'preferred_brands': preferences['preferred_brands'],
                'avg_price_range': preferences['avg_price_range'],
                'ai_readiness_score': min(engagement_score + (total_searches / 100.0), 1.0)
            }
            
        except Exception as e:
            logger.error(f"Error getting user AI profile: {str(e)}")
            return None
    
    @staticmethod
    def optimize_user_experience(user):
        """
        Optimize user experience based on AI insights
        Returns personalization settings and recommendations
        """
        try:
            ai_profile = UserAIService.get_user_ai_profile(user)
            
            if not ai_profile:
                return {
                    'personalization_level': 'basic',
                    'recommendations_enabled': True,
                    'price_alerts_enabled': True,
                    'ui_preferences': {}
                }
            
            # Determine personalization level
            personalization_level = 'advanced'
            if ai_profile['ai_readiness_score'] < 0.3:
                personalization_level = 'basic'
            elif ai_profile['ai_readiness_score'] < 0.7:
                personalization_level = 'intermediate'
            
            # Generate UI preferences
            ui_preferences = {
                'default_sort': 'relevance' if ai_profile['engagement_score'] > 0.5 else 'price_low',
                'show_price_predictions': ai_profile['price_sensitivity'] == 'high',
                'show_deal_alerts': ai_profile['price_sensitivity'] in ['high', 'medium'],
                'recommendation_frequency': 'high' if ai_profile['engagement_score'] > 0.7 else 'medium'
            }
            
            return {
                'personalization_level': personalization_level,
                'recommendations_enabled': True,
                'price_alerts_enabled': ai_profile['price_sensitivity'] != 'low',
                'ui_preferences': ui_preferences,
                'ai_profile': ai_profile
            }
            
        except Exception as e:
            logger.error(f"Error optimizing user experience: {str(e)}")
            return {
                'personalization_level': 'basic',
                'recommendations_enabled': True,
                'price_alerts_enabled': True,
                'ui_preferences': {}
            }
