"""
Celery Tasks for AI Engine
Asynchronous processing for AI operations
"""

from celery import shared_task
from django.core.cache import cache
from django.contrib.auth.models import User
from django.db.models import Q, Count
from datetime import datetime, timedelta
import logging

from ..core.models import Product, Offer, Merchant, Cart, CartItem, Notification, PriceHistory
from .integrations import ai_integration

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def train_ai_models(self):
    """
    Train all AI models with real datasets
    Runs periodically to update models with new data
    """
    try:
        logger.info("Starting AI model training...")
        
        # Reinitialize AI integration with fresh data
        ai_integration._initialize_models()
        
        logger.info("AI model training completed successfully")
        return {'status': 'success', 'message': 'All AI models trained successfully'}
        
    except Exception as e:
        logger.error(f"Error training AI models: {str(e)}")
        return {'status': 'error', 'message': str(e)}

@shared_task(bind=True, max_retries=2)
def process_product_image(self, user_id, image_data, image_name):
    """
    Process product image for identification
    Asynchronous image processing to avoid blocking
    """
    try:
        logger.info(f"Processing image {image_name} for user {user_id}")
        
        # Get user
        user = User.objects.get(id=user_id)
        
        # Identify product from image
        result = ai_integration.identify_product_from_image(image_data)
        
        if result['found']:
            # Create notification for user
            notification = Notification.objects.create(
                user=user,
                title='Product Identified',
                message=f'Found {len(result["products"])} matching products from your image',
                notification_type='image_identification',
                metadata={
                    'image_name': image_name,
                    'products_found': len(result['products']),
                    'identification_confidence': result.get('identification_info', {}).get('confidence', 0)
                }
            )
            
            # Cache result
            cache_key = f"image_identification_{user_id}_{hash(image_name)}"
            cache.set(cache_key, result, timeout=3600)  # 1 hour cache
        
        logger.info(f"Image processing completed for user {user_id}")
        return {
            'status': 'success',
            'user_id': user_id,
            'products_found': len(result.get('products', []))
        }
        
    except Exception as e:
        logger.error(f"Error processing product image: {str(e)}")
        return {'status': 'error', 'message': str(e)}

@shared_task(bind=True, max_retries=2)
def optimize_user_basket_async(self, user_id):
    """
    Optimize user's basket asynchronously
    """
    try:
        logger.info(f"Starting basket optimization for user {user_id}")
        
        # Get user
        user = User.objects.get(id=user_id)
        
        # Get cart items
        cart_items = CartItem.objects.filter(cart__user=user).select_related('product')
        
        if not cart_items.exists():
            logger.info(f"User {user_id} has empty cart, skipping optimization")
            return {'status': 'skipped', 'message': 'Empty cart'}
        
        # Perform optimization
        optimization_result = ai_integration.optimize_basket(user, cart_items)
        
        if 'error' not in optimization_result:
            # Create notification if significant savings
            if optimization_result.get('total_savings', 0) > 100:
                Notification.objects.create(
                    user=user,
                    title='Basket Optimized',
                    message=f'Save ₹{optimization_result["total_savings"]:.2f} by optimizing your basket',
                    notification_type='basket_optimization',
                    metadata=optimization_result
                )
        
        # Cache result
        cache_key = f"basket_optimization_{user_id}"
        cache.set(cache_key, optimization_result, timeout=1800)  # 30 minutes cache
        
        logger.info(f"Basket optimization completed for user {user_id}")
        return {
            'status': 'success',
            'user_id': user_id,
            'total_savings': optimization_result.get('total_savings', 0)
        }
        
    except Exception as e:
        logger.error(f"Error optimizing basket for user {user_id}: {str(e)}")
        return {'status': 'error', 'message': str(e)}

@shared_task(bind=True, max_retries=2)
def generate_price_predictions(self, product_ids, days_ahead=7):
    """
    Generate price predictions for products
    """
    try:
        logger.info(f"Generating price predictions for {len(product_ids)} products")
        
        # Get predictions
        predictions = ai_integration.predict_price_trends(product_ids, days_ahead)
        
        # Process predictions and create alerts if needed
        alerts_created = 0
        for product_id, prediction in predictions.items():
            if prediction['trend'] == 'dropping' and prediction['confidence'] > 0.7:
                # Find users who have this product in cart or watched
                interested_users = User.objects.filter(
                    Q(cartitem__product__id=product_id) |
                    Q(useractivity__product__id=product_id, useractivity__activity_type='product_view')
                ).distinct()
                
                for user in interested_users:
                    Notification.objects.create(
                        user=user,
                        title='Price Drop Alert',
                        message=f'Price for product ID {product_id} expected to drop by ₹{prediction.get("potential_savings", 0):.2f}',
                        notification_type='price_drop',
                        metadata={
                            'product_id': product_id,
                            'prediction': prediction
                        }
                    )
                    alerts_created += 1
        
        # Cache predictions
        cache_key = f"price_predictions_{hash(str(product_ids))}_{days_ahead}"
        cache.set(cache_key, predictions, timeout=3600)  # 1 hour cache
        
        logger.info(f"Price predictions completed, {alerts_created} alerts created")
        return {
            'status': 'success',
            'products_processed': len(product_ids),
            'alerts_created': alerts_created
        }
        
    except Exception as e:
        logger.error(f"Error generating price predictions: {str(e)}")
        return {'status': 'error', 'message': str(e)}

@shared_task(bind=True, max_retries=2)
def update_merchant_insights(self, merchant_id):
    """
    Update AI insights for merchant
    """
    try:
        logger.info(f"Updating insights for merchant {merchant_id}")
        
        from ..merchants.services_ai import MerchantAIService
        
        # Get merchant
        merchant = Merchant.objects.get(id=merchant_id)
        
        # Generate insights
        pricing_suggestions = MerchantAIService.get_pricing_suggestions(merchant)
        demand_forecast = MerchantAIService.get_demand_forecast(merchant)
        competitor_analysis = MerchantAIService.get_competitor_analysis(merchant)
        inventory_optimization = MerchantAIService.optimize_inventory(merchant)
        performance_insights = MerchantAIService.get_performance_insights(merchant)
        
        # Cache insights
        insights = {
            'pricing_suggestions': pricing_suggestions,
            'demand_forecast': demand_forecast,
            'competitor_analysis': competitor_analysis,
            'inventory_optimization': inventory_optimization,
            'performance_insights': performance_insights,
            'updated_at': datetime.now().isoformat()
        }
        
        cache_key = f"merchant_insights_{merchant_id}"
        cache.set(cache_key, insights, timeout=7200)  # 2 hours cache
        
        logger.info(f"Merchant insights updated for {merchant_id}")
        return {
            'status': 'success',
            'merchant_id': merchant_id,
            'insights_generated': len(insights)
        }
        
    except Exception as e:
        logger.error(f"Error updating merchant insights: {str(e)}")
        return {'status': 'error', 'message': str(e)}

@shared_task(bind=True, max_retries=1)
def generate_smart_notifications(self):
    """
    Generate smart notifications for all users
    Runs periodically to create personalized notifications
    """
    try:
        logger.info("Generating smart notifications for all users")
        
        # Get active users (users with activity in last 30 days)
        active_users = User.objects.filter(
            useractivity__created_at__gte=datetime.now() - timedelta(days=30)
        ).distinct()
        
        notifications_created = 0
        
        for user in active_users:
            # Generate smart notifications
            smart_notifications = ai_integration.generate_smart_notifications(user)
            
            # Create notifications in database
            for notification_data in smart_notifications:
                # Check if similar notification already exists
                existing = Notification.objects.filter(
                    user=user,
                    title=notification_data['title'],
                    notification_type=notification_data['type'],
                    created_at__gte=datetime.now() - timedelta(hours=24)
                ).exists()
                
                if not existing:
                    Notification.objects.create(
                        user=user,
                        title=notification_data['title'],
                        message=notification_data['message'],
                        notification_type=notification_data['type'],
                        priority=notification_data['priority'],
                        metadata=notification_data.get('data', {}),
                        product=notification_data.get('product')
                    )
                    notifications_created += 1
        
        logger.info(f"Smart notifications generated: {notifications_created} notifications created")
        return {
            'status': 'success',
            'users_processed': len(active_users),
            'notifications_created': notifications_created
        }
        
    except Exception as e:
        logger.error(f"Error generating smart notifications: {str(e)}")
        return {'status': 'error', 'message': str(e)}

@shared_task(bind=True, max_retries=2)
def process_price_history_update(self):
    """
    Process price history updates for ML models
    """
    try:
        logger.info("Processing price history updates")
        
        # Get recent price changes
        recent_offers = Offer.objects.filter(
            updated_at__gte=datetime.now() - timedelta(hours=1)
        ).select_related('product', 'merchant')
        
        history_records = []
        for offer in recent_offers:
            # Create price history record
            PriceHistory.objects.get_or_create(
                product=offer.product,
                merchant=offer.merchant,
                price=offer.price,
                defaults={
                    'original_price': offer.original_price,
                    'discount_percentage': offer.discount_percentage
                }
            )
            history_records.append(offer.product.id)
        
        # Check if we need to retrain models
        total_history = PriceHistory.objects.count()
        if total_history % 100 == 0:  # Every 100 new records
            # Trigger model retraining
            train_ai_models.delay()
        
        logger.info(f"Price history updated: {len(history_records)} records processed")
        return {
            'status': 'success',
            'records_processed': len(history_records),
            'total_history': total_history
        }
        
    except Exception as e:
        logger.error(f"Error processing price history: {str(e)}")
        return {'status': 'error', 'message': str(e)}

@shared_task(bind=True, max_retries=2)
def cleanup_ai_cache(self):
    """
    Clean up expired AI cache entries
    """
    try:
        logger.info("Cleaning up AI cache")
        
        # Define cache patterns to clean
        cache_patterns = [
            'ranked_products_*',
            'basket_optimization_*',
            'price_predictions_*',
            'merchant_insights_*',
            'image_identification_*',
            'user_preferences_*'
        ]
        
        # This would require custom cache backend implementation
        # For now, we'll let Redis handle TTL automatically
        
        logger.info("AI cache cleanup completed")
        return {'status': 'success', 'message': 'Cache cleanup completed'}
        
    except Exception as e:
        logger.error(f"Error cleaning up AI cache: {str(e)}")
        return {'status': 'error', 'message': str(e)}

# Periodic task schedule setup
from celery.schedules import crontab

# Schedule periodic tasks
periodic_tasks = {
    'train_models': {
        'task': 'apps.ai_engine.tasks.train_ai_models',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
        'options': {'queue': 'ai_training'}
    },
    'generate_notifications': {
        'task': 'apps.ai_engine.tasks.generate_smart_notifications',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
        'options': {'queue': 'notifications'}
    },
    'update_price_history': {
        'task': 'apps.ai_engine.tasks.process_price_history_update',
        'schedule': crontab(minute='*/15'),  # Every 15 minutes
        'options': {'queue': 'price_updates'}
    },
    'cleanup_cache': {
        'task': 'apps.ai_engine.tasks.cleanup_ai_cache',
        'schedule': crontab(hour=3, minute=0),  # Daily at 3 AM
        'options': {'queue': 'maintenance'}
    }
}
