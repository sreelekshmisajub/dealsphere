"""
Services layer for Merchants app
"""

import logging
from django.db.models import Count, Avg, Sum, Q, F
from django.db.models.functions import TruncDate
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal
from apps.core.models import Merchant, Offer, Product, PriceMatchRequest, OrderItem, UserActivity

logger = logging.getLogger(__name__)

class MerchantService:
    """Merchant service for business logic"""
    
    @staticmethod
    def get_merchant_analytics(merchant):
        """Get comprehensive merchant analytics"""
        try:
            # Time ranges
            now = timezone.now()
            week_ago = now - timedelta(days=7)
            
            # Offer analytics
            total_offers = Offer.objects.filter(merchant=merchant).count()
            active_offers = Offer.objects.filter(merchant=merchant, is_active=True).count()
            
            # Price match analytics
            total_price_matches = PriceMatchRequest.objects.filter(merchant=merchant).count()
            pending_price_matches = PriceMatchRequest.objects.filter(
                merchant=merchant, status='pending'
            ).count()
            approved_price_matches = PriceMatchRequest.objects.filter(
                merchant=merchant, status='approved'
            ).count()
            
            # Sales analytics (from order items)
            sales_data = OrderItem.objects.filter(merchant=merchant)
            
            total_sales = sales_data.aggregate(
                total=Sum(F('price') * F('quantity'))
            )['total'] or Decimal('0')
            
            total_orders = sales_data.values('order').distinct().count()
            
            # Recent sales
            recent_sales = sales_data.filter(
                order__created_at__gte=week_ago
            ).aggregate(
                total=Sum(F('price') * F('quantity')),
                count=Sum('quantity')
            )
            
            # Top performing products
            top_products = sales_data.values(
                'product__name'
            ).annotate(
                total_sales=Sum(F('price') * F('quantity')),
                quantity_sold=Sum('quantity')
            ).order_by('-total_sales')[:5]
            
            # Price match approval rate
            approval_rate = 0
            if total_price_matches > 0:
                approval_rate = (approved_price_matches / total_price_matches) * 100
            
            # Activity summary
            recent_activities = UserActivity.objects.filter(
                merchant=merchant,
                created_at__gte=week_ago
            ).values('activity_type').annotate(count=Count('id'))
            
            return {
                'overview': {
                    'total_offers': total_offers,
                    'active_offers': active_offers,
                    'total_products': Product.objects.filter(offers__merchant=merchant).distinct().count(),
                    'rating': float(merchant.rating),
                    'total_reviews': merchant.total_reviews
                },
                'sales': {
                    'total_sales': float(total_sales),
                    'total_orders': total_orders,
                    'recent_week_sales': float(recent_sales['total'] or 0),
                    'recent_week_quantity': int(recent_sales['count'] or 0),
                    'average_order_value': float(total_sales / total_orders) if total_orders > 0 else 0
                },
                'price_matches': {
                    'total_requests': total_price_matches,
                    'pending': pending_price_matches,
                    'approved': approved_price_matches,
                    'approval_rate': round(approval_rate, 2)
                },
                'top_products': list(top_products),
                'recent_activities': list(recent_activities),
                'last_updated': timezone.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting merchant analytics: {e}")
            return {}
    
    @staticmethod
    def get_merchant_performance(merchant, days=30):
        """Get merchant performance metrics"""
        try:
            cutoff_date = timezone.now() - timedelta(days=days)
            
            # Sales performance
            sales_data = OrderItem.objects.filter(
                merchant=merchant,
                order__created_at__gte=cutoff_date
            )
            
            daily_sales = sales_data.annotate(
                day=TruncDate('order__created_at')
            ).values('day').annotate(
                daily_revenue=Sum(F('price') * F('quantity')),
                daily_orders=Count('order', distinct=True),
                daily_items=Sum('quantity')
            ).order_by('day')
            
            # Product performance is derived from real order items and recorded merchant activities.
            product_order_rows = sales_data.values('product_id', 'product__name').annotate(
                revenue=Sum(F('price') * F('quantity')),
                orders=Count('order', distinct=True),
                quantity=Sum('quantity'),
            )
            activity_counts = {
                row['product_id']: row['views']
                for row in UserActivity.objects.filter(
                    merchant=merchant,
                    activity_type='product_view',
                    created_at__gte=cutoff_date,
                    product_id__isnull=False,
                ).values('product_id').annotate(views=Count('id'))
            }
            offer_performance = [
                {
                    'product__name': row['product__name'],
                    'views': activity_counts.get(row['product_id'], 0),
                    'orders': row['orders'],
                    'quantity': row['quantity'] or 0,
                    'revenue': float(row['revenue'] or 0),
                }
                for row in product_order_rows
            ]
            offer_performance.sort(key=lambda item: (item['orders'], item['revenue']), reverse=True)
            
            return {
                'daily_sales': list(daily_sales),
                'offer_performance': offer_performance,
                'period_days': days
            }
            
        except Exception as e:
            logger.error(f"Error getting merchant performance: {e}")
            return {}
    
    @staticmethod
    def suggest_pricing(merchant, product_id):
        """Suggest optimal pricing for product"""
        try:
            product = Product.objects.get(id=product_id)
            
            # Get competitor prices
            competitor_offers = Offer.objects.filter(
                product=product,
                is_active=True
            ).exclude(merchant=merchant).order_by('price')
            
            # Get merchant's current offer
            current_offer = Offer.objects.filter(
                product=product,
                merchant=merchant,
                is_active=True
            ).first()
            
            # Calculate suggested price
            if competitor_offers.exists():
                prices = list(competitor_offers.values_list('price', flat=True))
                avg_price = sum(prices) / len(prices)
                min_price = min(prices)
                max_price = max(prices)
                
                # Suggest price 5% below average
                suggested_price = avg_price * Decimal('0.95')
                
                # Ensure it's not below minimum profit margin
                min_profit_price = suggested_price * Decimal('0.8')  # 20% minimum margin
                
                final_suggestion = max(min_profit_price, min_price * Decimal('0.9'))
                
            else:
                # No competitors, use Amazon/Flipkart prices
                prices = []
                if product.amazon_price:
                    prices.append(product.amazon_price)
                if product.flipkart_price:
                    prices.append(product.flipkart_price)
                
                if prices:
                    final_suggestion = min(prices) * Decimal('0.9')
                else:
                    final_suggestion = current_offer.price * Decimal('0.95') if current_offer else Decimal('1000')
            
            return {
                'product': product.name,
                'current_price': float(current_offer.price) if current_offer else None,
                'suggested_price': round(final_suggestion, 2),
                'competitor_count': competitor_offers.count(),
                'lowest_competitor_price': float(competitor_offers.first().price) if competitor_offers.exists() else None,
                'average_competitor_price': float(sum(prices) / len(prices)) if competitor_offers.exists() else None,
                'potential_savings': round(float(current_offer.price - final_suggestion), 2) if current_offer else None
            }
            
        except Product.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Error suggesting pricing: {e}")
            return None

class ProductService:
    """Product service for merchants"""
    
    @staticmethod
    def create_product_from_barcode(merchant, barcode_data):
        """Create product from barcode data"""
        try:
            # Check if product already exists
            if Product.objects.filter(barcode=barcode_data.get('barcode')).exists():
                existing_product = Product.objects.get(barcode=barcode_data.get('barcode'))
                
                # Create offer for existing product
                offer = Offer.objects.create(
                    product=existing_product,
                    merchant=merchant,
                    price=barcode_data.get('price', 0),
                    original_price=barcode_data.get('original_price'),
                    delivery_time_hours=barcode_data.get('delivery_time_hours', 24)
                )
                
                return existing_product, offer
            
            # Create new product
            product_data = {
                'name': barcode_data.get('name'),
                'barcode': barcode_data.get('barcode'),
                'category_id': barcode_data.get('category_id'),
                'brand_id': barcode_data.get('brand_id'),
                'description': barcode_data.get('description'),
                'image_url': barcode_data.get('image_url')
            }
            
            # Remove None values
            product_data = {k: v for k, v in product_data.items() if v is not None}
            
            product = Product.objects.create(**product_data)
            
            # Create offer
            offer = Offer.objects.create(
                product=product,
                merchant=merchant,
                price=barcode_data.get('price', 0),
                original_price=barcode_data.get('original_price'),
                delivery_time_hours=barcode_data.get('delivery_time_hours', 24)
            )
            
            return product, offer
            
        except Exception as e:
            logger.error(f"Error creating product from barcode: {e}")
            return None, None
    
    @staticmethod
    def get_merchant_inventory(merchant):
        """Get merchant's inventory summary"""
        try:
            offers = Offer.objects.filter(merchant=merchant, is_active=True)
            
            inventory_data = []
            
            for offer in offers:
                product = offer.product
                competitor_offers = Offer.objects.filter(
                    product=product,
                    is_active=True
                ).exclude(merchant=merchant)
                
                # Calculate price position
                if competitor_offers.exists():
                    prices = list(competitor_offers.values_list('price', flat=True))
                    price_position = 'low' if offer.price <= min(prices) else 'high' if offer.price >= max(prices) else 'medium'
                else:
                    price_position = 'unique'
                
                inventory_data.append({
                    'product_id': product.id,
                    'product_name': product.name,
                    'barcode': product.barcode,
                    'category': product.category.name if product.category else None,
                    'brand': product.brand.name if product.brand else None,
                    'current_price': float(offer.price),
                    'original_price': float(offer.original_price) if offer.original_price else None,
                    'discount_percentage': offer.discount_percentage,
                    'stock_quantity': offer.stock_quantity,
                    'delivery_time_hours': offer.delivery_time_hours,
                    'price_position': price_position,
                    'competitor_count': competitor_offers.count(),
                    'lowest_competitor_price': float(min(prices)) if competitor_offers.exists() else None,
                    'created_at': offer.created_at
                })
            
            return inventory_data
            
        except Exception as e:
            logger.error(f"Error getting merchant inventory: {e}")
            return []
    
    @staticmethod
    def get_low_stock_alerts(merchant):
        """Get low stock alerts for merchant"""
        try:
            low_stock_offers = Offer.objects.filter(
                merchant=merchant,
                is_active=True,
                stock_quantity__lte=5  # Alert when stock <= 5
            ).order_by('stock_quantity')
            
            alerts = []
            for offer in low_stock_offers:
                alerts.append({
                    'product_id': offer.product.id,
                    'product_name': offer.product.name,
                    'current_stock': offer.stock_quantity,
                    'alert_level': 'critical' if offer.stock_quantity <= 2 else 'warning',
                    'last_updated': offer.updated_at
                })
            
            return alerts
            
        except Exception as e:
            logger.error(f"Error getting low stock alerts: {e}")
            return []

class PriceMatchService:
    """Price match service for merchants"""
    
    @staticmethod
    def evaluate_price_match_request(price_match_request):
        """Evaluate price match request with AI"""
        try:
            requested_price = price_match_request.requested_price
            product = price_match_request.product
            merchant = price_match_request.merchant
            
            # Get merchant's current offer
            current_offer = Offer.objects.filter(
                product=product,
                merchant=merchant,
                is_active=True
            ).first()
            
            if not current_offer:
                return {
                    'recommendation': 'reject',
                    'reason': 'No active offer found for this product',
                    'confidence': 1.0
                }
            
            # Get market prices
            market_offers = Offer.objects.filter(
                product=product,
                is_active=True
            ).order_by('price')
            
            # Calculate price position
            prices = list(market_offers.values_list('price', flat=True))
            if prices:
                price_percentile = (prices.index(current_offer.price) / len(prices)) * 100
            else:
                price_percentile = 50
            
            # Evaluate request
            price_difference = current_offer.price - requested_price
            price_difference_percent = (price_difference / current_offer.price) * 100
            
            # Decision logic
            if price_difference_percent <= 5:  # Less than 5% difference
                recommendation = 'approve'
                confidence = 0.9
                reason = 'Price difference is minimal'
            elif price_difference_percent <= 15:  # 5-15% difference
                if price_percentile >= 70:  # Merchant is already expensive
                    recommendation = 'approve'
                    confidence = 0.7
                    reason = 'Competitive pricing needed'
                else:
                    recommendation = 'reject'
                    confidence = 0.6
                    reason = 'Current price is competitive'
            else:  # More than 15% difference
                recommendation = 'reject'
                confidence = 0.8
                reason = 'Price difference too large'
            
            return {
                'recommendation': recommendation,
                'reason': reason,
                'confidence': confidence,
                'current_price': float(current_offer.price),
                'requested_price': float(requested_price),
                'price_difference': float(price_difference),
                'price_difference_percent': round(price_difference_percent, 2),
                'market_position_percentile': round(price_percentile, 2)
            }
            
        except Exception as e:
            logger.error(f"Error evaluating price match: {e}")
            return {
                'recommendation': 'reject',
                'reason': 'Error evaluating request',
                'confidence': 0.0
            }
