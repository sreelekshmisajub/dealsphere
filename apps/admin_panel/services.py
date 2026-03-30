"""
Services layer for Admin Panel app
"""

import logging
import os
from django.db.models import Count, Avg, Sum, Q, F
from django.utils import timezone
from datetime import timedelta, date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.conf import settings
from apps.core.models import User, Merchant, Product, Offer, PriceMatchRequest, Order, OrderItem, UserActivity

logger = logging.getLogger(__name__)

class AdminService:
    """Admin service for business logic"""
    
    @staticmethod
    def get_dashboard_data():
        """Get comprehensive dashboard data"""
        try:
            # Time ranges
            now = timezone.now()
            week_ago = now - timedelta(days=7)
            month_ago = now - timedelta(days=30)
            
            # Overview stats
            total_users = User.objects.count()
            total_merchants = Merchant.objects.count()
            total_products = Product.objects.count()
            total_offers = Offer.objects.filter(is_active=True).count()
            
            # Recent stats
            new_users_week = User.objects.filter(date_joined__gte=week_ago).count()
            new_merchants_week = Merchant.objects.filter(created_at__gte=week_ago).count()
            new_products_week = Product.objects.filter(created_at__gte=week_ago).count()
            new_offers_week = Offer.objects.filter(created_at__gte=week_ago).count()
            
            # User statistics
            user_stats = {
                'total': total_users,
                'active': User.objects.filter(is_active=True).count(),
                'merchants': User.objects.filter(is_merchant=True).count(),
                'verified': User.objects.filter(is_verified=True).count(),
                'new_this_week': new_users_week,
                'new_this_month': User.objects.filter(date_joined__gte=month_ago).count()
            }
            
            # Merchant statistics
            merchant_stats = {
                'total': total_merchants,
                'verified': Merchant.objects.filter(verified=True).count(),
                'unverified': Merchant.objects.filter(verified=False).count(),
                'avg_rating': float(Merchant.objects.aggregate(avg=Avg('rating'))['avg'] or 0),
                'new_this_week': new_merchants_week,
                'with_active_offers': Merchant.objects.filter(offers__is_active=True).distinct().count()
            }
            
            # Product statistics
            product_stats = {
                'total': total_products,
                'with_barcode': Product.objects.filter(barcode__isnull=False).exclude(barcode='').count(),
                'with_offers': Product.objects.filter(offers__is_active=True).distinct().count(),
                'avg_amazon_price': float(Product.objects.aggregate(avg=Avg('amazon_price'))['avg'] or 0),
                'avg_flipkart_price': float(Product.objects.aggregate(avg=Avg('flipkart_price'))['avg'] or 0),
                'new_this_week': new_products_week
            }
            
            # Offer statistics
            offer_stats = {
                'total': total_offers,
                'active': Offer.objects.filter(is_active=True).count(),
                'avg_price': float(Offer.objects.filter(is_active=True).aggregate(avg=Avg('price'))['avg'] or 0),
                'avg_delivery_time': float(Offer.objects.filter(is_active=True).aggregate(avg=Avg('delivery_time_hours'))['avg'] or 0),
                'with_discount': Offer.objects.filter(is_active=True, discount_percentage__isnull=False).count(),
                'new_this_week': new_offers_week
            }
            
            # Price match statistics
            price_match_stats = {
                'total': PriceMatchRequest.objects.count(),
                'pending': PriceMatchRequest.objects.filter(status='pending').count(),
                'approved': PriceMatchRequest.objects.filter(status='approved').count(),
                'rejected': PriceMatchRequest.objects.filter(status='rejected').count(),
                'expired': PriceMatchRequest.objects.filter(status='expired').count(),
                'approval_rate': AdminService._calculate_approval_rate(),
                'new_this_week': PriceMatchRequest.objects.filter(created_at__gte=week_ago).count()
            }
            
            # Recent activities
            recent_activities = UserActivity.objects.select_related(
                'user', 'product', 'merchant'
            ).order_by('-created_at')[:20]
            
            activity_data = []
            for activity in recent_activities:
                data = {
                    'id': activity.id,
                    'user_email': activity.user.email,
                    'activity_type': activity.activity_type,
                    'created_at': activity.created_at,
                    'metadata': activity.metadata
                }
                
                if activity.product:
                    data['product_name'] = activity.product.name
                
                if activity.merchant:
                    data['merchant_name'] = activity.merchant.shop_name
                
                activity_data.append(data)
            
            # System health
            system_health = AdminService.get_system_health()
            
            return {
                'overview': {
                    'total_users': total_users,
                    'total_merchants': total_merchants,
                    'total_products': total_products,
                    'total_offers': total_offers,
                    'new_users_week': new_users_week,
                    'new_merchants_week': new_merchants_week,
                    'new_products_week': new_products_week,
                    'new_offers_week': new_offers_week
                },
                'user_stats': user_stats,
                'merchant_stats': merchant_stats,
                'product_stats': product_stats,
                'offer_stats': offer_stats,
                'price_match_stats': price_match_stats,
                'recent_activities': activity_data,
                'system_health': system_health,
                'last_updated': timezone.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting dashboard data: {e}")
            return {}
    
    @staticmethod
    def get_analytics():
        """Get detailed analytics"""
        try:
            # User growth over time
            user_growth = AdminService._get_user_growth()
            
            # Merchant performance
            merchant_performance = AdminService._get_merchant_performance()
            
            # Product category distribution
            category_distribution = AdminService._get_category_distribution()
            
            # Price match trends
            price_match_trends = AdminService._get_price_match_trends()
            
            # Geographic distribution
            geographic_data = AdminService._get_geographic_distribution()
            
            return {
                'user_growth': user_growth,
                'merchant_performance': merchant_performance,
                'category_distribution': category_distribution,
                'price_match_trends': price_match_trends,
                'geographic_distribution': geographic_data
            }
            
        except Exception as e:
            logger.error(f"Error getting analytics: {e}")
            return {}
    
    @staticmethod
    def get_system_health():
        """Get system health status"""
        try:
            # Database connectivity
            db_status = 'healthy'
            try:
                User.objects.count()
            except:
                db_status = 'unhealthy'
            
            # Recent activity
            recent_activity = UserActivity.objects.filter(
                created_at__gte=timezone.now() - timedelta(hours=1)
            ).count()

            storage_usage = {
                'database_size_bytes': AdminService._safe_file_size(settings.DATABASES['default']['NAME']),
                'media_size_bytes': AdminService._directory_size(settings.MEDIA_ROOT),
            }
            storage_usage['total_size_bytes'] = storage_usage['database_size_bytes'] + storage_usage['media_size_bytes']
            
            # Overall status
            overall_status = 'healthy'
            if db_status != 'healthy':
                overall_status = 'degraded'
            
            return {
                'overall_status': overall_status,
                'database': db_status,
                'recent_activity_count': recent_activity,
                'error_rate': None,
                'avg_response_time_ms': None,
                'storage_usage': storage_usage,
                'last_check': timezone.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting system health: {e}")
            return {
                'overall_status': 'unhealthy',
                'error': str(e),
                'last_check': timezone.now().isoformat()
            }

    @staticmethod
    def _safe_file_size(path):
        try:
            return os.path.getsize(path)
        except OSError:
            return 0

    @staticmethod
    def _directory_size(path):
        total = 0
        if not path or not os.path.exists(path):
            return total

        for root, _, files in os.walk(path):
            for filename in files:
                try:
                    total += os.path.getsize(os.path.join(root, filename))
                except OSError:
                    continue
        return total
    
    @staticmethod
    def _calculate_approval_rate():
        """Calculate price match approval rate"""
        total = PriceMatchRequest.objects.count()
        if total == 0:
            return 0
        
        approved = PriceMatchRequest.objects.filter(status='approved').count()
        return round((approved / total) * 100, 2)
    
    @staticmethod
    def _get_user_growth():
        """Get user growth data"""
        try:
            # Last 30 days user growth
            growth_data = []
            for i in range(30):
                date = timezone.now().date() - timedelta(days=i)
                count = User.objects.filter(date_joined__date=date).count()
                growth_data.append({
                    'date': date.isoformat(),
                    'new_users': count
                })
            
            return list(reversed(growth_data))
            
        except Exception as e:
            logger.error(f"Error getting user growth: {e}")
            return []
    
    @staticmethod
    def _get_merchant_performance():
        """Get merchant performance data"""
        try:
            performance_data = []
            merchants = Merchant.objects.select_related('user').order_by('-rating', 'shop_name')[:50]

            for merchant in merchants:
                order_totals = OrderItem.objects.filter(merchant=merchant).aggregate(
                    total_sales=Sum('price'),
                    total_orders=Count('order', distinct=True),
                )
                performance_data.append({
                    'merchant_id': merchant.id,
                    'shop_name': merchant.shop_name,
                    'total_sales': float(order_totals['total_sales'] or 0),
                    'total_orders': order_totals['total_orders'] or 0,
                    'offer_count': merchant.offers.filter(is_active=True).count(),
                    'rating': float(merchant.rating),
                    'verified': merchant.verified,
                })

            performance_data.sort(key=lambda item: (item['total_sales'], item['total_orders'], item['rating']), reverse=True)
            return performance_data[:10]
            
        except Exception as e:
            logger.error(f"Error getting merchant performance: {e}")
            return []
    
    @staticmethod
    def _get_category_distribution():
        """Get product category distribution"""
        try:
            category_data = []
            from apps.core.models import Category

            categories = Category.objects.annotate(
                product_count=Count('products')
            ).order_by('-product_count')[:10]
            
            for category in categories:
                category_data.append({
                    'category_id': category.id,
                    'category_name': category.name,
                    'product_count': category.product_count,
                    'level': category.level
                })
            
            return category_data
            
        except Exception as e:
            logger.error(f"Error getting category distribution: {e}")
            return []
    
    @staticmethod
    def _get_price_match_trends():
        """Get price match trends"""
        try:
            # Last 30 days price match trends
            trends_data = []
            for i in range(30):
                date = timezone.now().date() - timedelta(days=i)
                requests = PriceMatchRequest.objects.filter(created_at__date=date)
                
                trends_data.append({
                    'date': date.isoformat(),
                    'total_requests': requests.count(),
                    'approved': requests.filter(status='approved').count(),
                    'rejected': requests.filter(status='rejected').count(),
                    'pending': requests.filter(status='pending').count()
                })
            
            return list(reversed(trends_data))
            
        except Exception as e:
            logger.error(f"Error getting price match trends: {e}")
            return []
    
    @staticmethod
    def _get_geographic_distribution():
        """Get geographic distribution of users and merchants"""
        try:
            # User distribution (simplified - would use proper geospatial queries in production)
            user_locations = User.objects.filter(
                location_lat__isnull=False,
                location_lng__isnull=False
            ).count()
            
            # Merchant distribution
            merchant_locations = Merchant.objects.filter(
                location_lat__isnull=False,
                location_lng__isnull=False
            ).count()
            
            return {
                'users_with_location': user_locations,
                'merchants_with_location': merchant_locations,
                'total_users': User.objects.count(),
                'total_merchants': Merchant.objects.count()
            }
            
        except Exception as e:
            logger.error(f"Error getting geographic distribution: {e}")
            return {}

class ReportService:
    """Report generation service"""
    
    @staticmethod
    def generate_user_report(format='json'):
        """Generate user report"""
        try:
            users = User.objects.all().order_by('-date_joined')
            
            if format == 'csv':
                import pandas as pd

                # Generate CSV data
                data = []
                for user in users:
                    data.append({
                        'ID': user.id,
                        'Username': user.username,
                        'Email': user.email,
                        'Name': f"{user.first_name} {user.last_name}".strip(),
                        'Phone': user.phone or '',
                        'Is Merchant': user.is_merchant,
                        'Is Verified': user.is_verified,
                        'Is Active': user.is_active,
                        'Date Joined': user.date_joined.date(),
                        'Last Login': user.last_login.date() if user.last_login else ''
                    })
                
                return pd.DataFrame(data)
            
            elif format == 'json':
                # Generate JSON data
                data = []
                for user in users:
                    data.append({
                        'id': user.id,
                        'username': user.username,
                        'email': user.email,
                        'full_name': f"{user.first_name} {user.last_name}".strip(),
                        'phone': user.phone,
                        'is_merchant': user.is_merchant,
                        'is_verified': user.is_verified,
                        'is_active': user.is_active,
                        'date_joined': user.date_joined.isoformat(),
                        'last_login': user.last_login.isoformat() if user.last_login else None
                    })
                
                return data
            
        except Exception as e:
            logger.error(f"Error generating user report: {e}")
            return None
    
    @staticmethod
    def generate_merchant_report(format='json'):
        """Generate merchant report"""
        try:
            merchants = Merchant.objects.select_related('user').order_by('-created_at')
            
            if format == 'csv':
                import pandas as pd

                data = []
                for merchant in merchants:
                    data.append({
                        'ID': merchant.id,
                        'Shop Name': merchant.shop_name,
                        'Email': merchant.user.email,
                        'Phone': merchant.user.phone,
                        'GSTIN': merchant.gstin or '',
                        'Verified': merchant.verified,
                        'Rating': merchant.rating,
                        'Total Reviews': merchant.total_reviews,
                        'Delivery Radius': merchant.delivery_radius_km,
                        'Created Date': merchant.created_at.date()
                    })
                
                return pd.DataFrame(data)
            
            elif format == 'json':
                data = []
                for merchant in merchants:
                    data.append({
                        'id': merchant.id,
                        'shop_name': merchant.shop_name,
                        'email': merchant.user.email,
                        'phone': merchant.user.phone,
                        'gstin': merchant.gstin,
                        'verified': merchant.verified,
                        'rating': float(merchant.rating),
                        'total_reviews': merchant.total_reviews,
                        'delivery_radius_km': merchant.delivery_radius_km,
                        'created_at': merchant.created_at.isoformat()
                    })
                
                return data
            
        except Exception as e:
            logger.error(f"Error generating merchant report: {e}")
            return None
