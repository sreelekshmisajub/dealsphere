"""
Services layer for API app
"""

import logging
from django.db.models import Q, Count, Avg, Min, Max
from django.utils import timezone
from datetime import timedelta
from apps.core.models import Product, Offer, Category, Brand, UserActivity

logger = logging.getLogger(__name__)

class APIService:
    """API service for business logic"""
    
    @staticmethod
    def search_products(query, category=None, min_price=None, max_price=None, sort_by='relevance', user=None):
        """Search products with real dataset integration"""
        try:
            queryset = Product.objects.all()
            
            # Text search
            if query:
                queryset = queryset.filter(
                    Q(name__icontains=query) |
                    Q(barcode__icontains=query) |
                    Q(brand__name__icontains=query) |
                    Q(category__name__icontains=query)
                )
            
            # Category filter
            if category:
                queryset = queryset.filter(category__name__icontains=category)
            
            # Price filter
            if min_price:
                queryset = queryset.filter(
                    Q(amazon_price__gte=min_price) | 
                    Q(flipkart_price__gte=min_price) |
                    Q(myntra_price__gte=min_price) |
                    Q(offers__price__gte=min_price)
                ).distinct()
            
            if max_price:
                queryset = queryset.filter(
                    Q(amazon_price__lte=max_price) | 
                    Q(flipkart_price__lte=max_price) |
                    Q(myntra_price__lte=max_price) |
                    Q(offers__price__lte=max_price)
                ).distinct()
            
            # Only products with active offers
            queryset = queryset.filter(offers__is_active=True).distinct()
            
            # Sorting
            if sort_by == 'price_low':
                queryset = queryset.annotate(
                    min_price=Min('offers__price')
                ).order_by('min_price')
            elif sort_by == 'price_high':
                queryset = queryset.annotate(
                    max_price=Max('offers__price')
                ).order_by('-max_price')
            elif sort_by == 'rating':
                queryset = queryset.annotate(
                    max_rating=Max('amazon_rating', 'flipkart_rating')
                ).order_by('-max_rating')
            elif sort_by == 'newest':
                queryset = queryset.order_by('-created_at')
            elif sort_by == 'popularity':
                # Sort by number of offers (proxy for popularity)
                queryset = queryset.annotate(
                    offer_count=Count('offers')
                ).order_by('-offer_count')
            else:  # relevance
                if query:
                    # Prioritize exact matches
                    queryset = queryset.annotate(
                        relevance=Count(
                            Case(
                                When(name__iexact=query, then=1),
                                When(barcode__iexact=query, then=1),
                                default=0,
                                output_field=IntegerField()
                            )
                        )
                    ).order_by('-relevance', '-created_at')
                else:
                    queryset = queryset.order_by('-created_at')
            
            # Track search activity
            if user:
                UserActivity.objects.create(
                    user=user,
                    activity_type='search',
                    metadata={
                        'query': query,
                        'category': category,
                        'min_price': min_price,
                        'max_price': max_price,
                        'sort_by': sort_by,
                        'results_count': queryset.count()
                    }
                )
            
            return queryset
            
        except Exception as e:
            logger.error(f"Error searching products: {e}")
            return Product.objects.none()
    
    @staticmethod
    def get_product_recommendations(user, limit=10):
        """Get personalized product recommendations"""
        try:
            # Get user's search and activity history
            recent_activities = UserActivity.objects.filter(
                user=user,
                activity_type__in=['search', 'product_view', 'add_to_cart'],
                created_at__gte=timezone.now() - timedelta(days=30)
            )
            
            # Extract preferences
            preferred_categories = set()
            preferred_brands = set()
            price_range = {'min': None, 'max': None}
            
            for activity in recent_activities:
                if activity.product:
                    if activity.product.category:
                        preferred_categories.add(activity.product.category)
                    if activity.product.brand:
                        preferred_brands.add(activity.product.brand)
                    
                    # Track price preferences
                    best_offer = activity.product.offers.filter(is_active=True).order_by('price').first()
                    if best_offer:
                        if price_range['min'] is None or best_offer.price < price_range['min']:
                            price_range['min'] = best_offer.price
                        if price_range['max'] is None or best_offer.price > price_range['max']:
                            price_range['max'] = best_offer.price
            
            # Build recommendation query
            queryset = Product.objects.filter(offers__is_active=True).distinct()
            
            # Apply preferences
            if preferred_categories:
                queryset = queryset.filter(category__in=preferred_categories)
            
            if preferred_brands:
                queryset = queryset.filter(brand__in=preferred_brands)
            
            # Apply price range
            if price_range['min']:
                queryset = queryset.filter(
                    Q(amazon_price__gte=price_range['min']) | 
                    Q(flipkart_price__gte=price_range['min']) |
                    Q(myntra_price__gte=price_range['min']) |
                    Q(offers__price__gte=price_range['min'])
                ).distinct()
            
            if price_range['max']:
                queryset = queryset.filter(
                    Q(amazon_price__lte=price_range['max']) | 
                    Q(flipkart_price__lte=price_range['max']) |
                    Q(myntra_price__lte=price_range['max']) |
                    Q(offers__price__lte=price_range['max'])
                ).distinct()
            
            # Exclude products already in cart
            if hasattr(user, 'cart') and user.cart:
                cart_product_ids = user.cart.items.values_list('product_id', flat=True)
                queryset = queryset.exclude(id__in=cart_product_ids)
            
            # Order by relevance and popularity
            queryset = queryset.annotate(
                offer_count=Count('offers'),
                avg_rating=Max('amazon_rating', 'flipkart_rating')
            ).order_by('-offer_count', '-avg_rating')
            
            return queryset[:limit]
            
        except Exception as e:
            logger.error(f"Error getting recommendations: {e}")
            return Product.objects.none()
    
    @staticmethod
    def get_trending_products(limit=10, days=7):
        """Get trending products based on activity"""
        try:
            cutoff = timezone.now() - timedelta(days=days)
            
            # Get products with most views in the period
            trending = Product.objects.filter(
                user_activities__activity_type='product_view',
                user_activities__created_at__gte=cutoff
            ).annotate(
                view_count=Count('user_activities')
            ).filter(
                offers__is_active=True
            ).order_by('-view_count')[:limit]
            
            return trending
            
        except Exception as e:
            logger.error(f"Error getting trending products: {e}")
            return Product.objects.none()
    
    @staticmethod
    def get_similar_products(product_id, limit=5):
        """Get similar products"""
        try:
            product = Product.objects.get(id=product_id)
            
            # Get products from same category or brand
            similar = Product.objects.filter(
                Q(category=product.category) | Q(brand=product.brand)
            ).exclude(id=product_id)
            
            # Only products with active offers
            similar = similar.filter(offers__is_active=True).distinct()
            
            # Order by similarity (same category first, then same brand)
            similar = similar.annotate(
                category_match=Case(
                    When(category=product.category, then=1),
                    default=0,
                    output_field=IntegerField()
                ),
                brand_match=Case(
                    When(brand=product.brand, then=1),
                    default=0,
                    output_field=IntegerField()
                )
            ).order_by('-category_match', '-brand_match', '-created_at')
            
            return similar[:limit]
            
        except Product.DoesNotExist:
            return Product.objects.none()
        except Exception as e:
            logger.error(f"Error getting similar products: {e}")
            return Product.objects.none()
    
    @staticmethod
    def get_price_comparison(product_id):
        """Get comprehensive price comparison"""
        try:
            product = Product.objects.get(id=product_id)
            
            comparison = {
                'product': {
                    'id': product.id,
                    'name': product.name,
                    'barcode': product.barcode,
                    'image_url': product.image_url
                },
                'sources': {}
            }
            
            # Amazon data
            if product.amazon_price:
                comparison['sources']['amazon'] = {
                    'price': float(product.amazon_price),
                    'url': product.amazon_url,
                    'rating': float(product.amazon_rating) if product.amazon_rating else None
                }
            
            # Flipkart data
            if product.flipkart_price:
                comparison['sources']['flipkart'] = {
                    'price': float(product.flipkart_price),
                    'url': product.flipkart_url,
                    'rating': float(product.flipkart_rating) if product.flipkart_rating else None
                }
            if product.myntra_price:
                comparison['sources']['myntra'] = {
                    'price': float(product.myntra_price),
                    'url': product.myntra_url,
                    'rating': float(product.myntra_rating) if product.myntra_rating else None
                }
            
            # Local store offers
            local_offers = []
            for offer in product.offers.filter(is_active=True).select_related('merchant'):
                local_offers.append({
                    'offer_id': offer.id,
                    'merchant': {
                        'id': offer.merchant.id,
                        'shop_name': offer.merchant.shop_name,
                        'rating': float(offer.merchant.rating),
                        'verified': offer.merchant.verified
                    },
                    'price': float(offer.price),
                    'original_price': float(offer.original_price) if offer.original_price else None,
                    'discount_percentage': offer.discount_percentage,
                    'delivery_time_hours': offer.delivery_time_hours,
                    'delivery_cost': float(offer.delivery_cost),
                    'stock_quantity': offer.stock_quantity
                })
            
            comparison['sources']['local_stores'] = local_offers
            
            # Calculate best price
            all_prices = []
            if product.amazon_price:
                all_prices.append(('amazon', product.amazon_price))
            if product.flipkart_price:
                all_prices.append(('flipkart', product.flipkart_price))
            if product.myntra_price:
                all_prices.append(('myntra', product.myntra_price))
            
            for offer in local_offers:
                all_prices.append(('local', offer['price']))
            
            if all_prices:
                best_source, best_price = min(all_prices, key=lambda x: x[1])
                comparison['best_price'] = {
                    'source': best_source,
                    'price': float(best_price)
                }
            
            return comparison
            
        except Product.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Error getting price comparison: {e}")
            return None
    
    @staticmethod
    def get_market_insights(category=None):
        """Get market insights and trends"""
        try:
            insights = {}
            
            # Product distribution by category
            category_stats = {}
            categories = Category.objects.annotate(
                product_count=Count('products'),
                avg_price=Avg('products__offers__price')
            ).filter(product_count__gt=0)
            
            if category:
                categories = categories.filter(name__icontains=category)
            
            for cat in categories:
                category_stats[cat.name] = {
                    'product_count': cat.product_count,
                    'avg_price': float(cat.avg_price) if cat.avg_price else 0
                }
            
            insights['category_distribution'] = category_stats
            
            # Price ranges
            offers = Offer.objects.filter(is_active=True)
            
            if category:
                offers = offers.filter(product__category__name__icontains=category)
            
            price_stats = offers.aggregate(
                min_price=Min('price'),
                max_price=Max('price'),
                avg_price=Avg('price'),
                total_offers=Count('id')
            )
            
            insights['price_statistics'] = {
                'min_price': float(price_stats['min_price'] or 0),
                'max_price': float(price_stats['max_price'] or 0),
                'avg_price': float(price_stats['avg_price'] or 0),
                'total_offers': price_stats['total_offers']
            }
            
            # Top brands
            brand_stats = Product.objects.filter(
                offers__is_active=True
            ).values('brand__name').annotate(
                product_count=Count('id'),
                avg_price=Avg('offers__price')
            ).order_by('-product_count')[:10]
            
            insights['top_brands'] = list(brand_stats)
            
            # Recent trends (simplified)
            recent_offers = offers.filter(
                created_at__gte=timezone.now() - timedelta(days=7)
            ).count()
            
            insights['recent_trends'] = {
                'new_offers_this_week': recent_offers,
                'growth_rate': (recent_offers / price_stats['total_offers'] * 100) if price_stats['total_offers'] > 0 else 0
            }
            
            return insights
            
        except Exception as e:
            logger.error(f"Error getting market insights: {e}")
            return {}

class SearchService:
    """Advanced search service"""
    
    @staticmethod
    def advanced_search(query, filters=None, sort_by='relevance', user=None):
        """Advanced product search with multiple filters"""
        try:
            queryset = Product.objects.all()
            
            # Text search
            if query:
                queryset = queryset.filter(
                    Q(name__icontains=query) |
                    Q(barcode__icontains=query) |
                    Q(brand__name__icontains=query) |
                    Q(category__name__icontains=query) |
                    Q(description__icontains=query)
                )
            
            # Apply filters
            if filters:
                # Category filter
                if filters.get('categories'):
                    categories = filters['categories']
                    if isinstance(categories, str):
                        categories = [categories]
                    queryset = queryset.filter(category__name__in=categories)
                
                # Brand filter
                if filters.get('brands'):
                    brands = filters['brands']
                    if isinstance(brands, str):
                        brands = [brands]
                    queryset = queryset.filter(brand__name__in=brands)
                
                # Price range
                if filters.get('price_min'):
                    queryset = queryset.filter(
                        Q(amazon_price__gte=filters['price_min']) | 
                        Q(flipkart_price__gte=filters['price_min']) |
                        Q(offers__price__gte=filters['price_min'])
                    ).distinct()
                
                if filters.get('price_max'):
                    queryset = queryset.filter(
                        Q(amazon_price__lte=filters['price_max']) | 
                        Q(flipkart_price__lte=filters['price_max']) |
                        Q(offers__price__lte=filters['price_max'])
                    ).distinct()
                
                # Rating filter
                if filters.get('min_rating'):
                    min_rating = float(filters['min_rating'])
                    queryset = queryset.filter(
                        Q(amazon_rating__gte=min_rating) | 
                        Q(flipkart_rating__gte=min_rating)
                    ).distinct()
                
                # Delivery time filter
                if filters.get('max_delivery_time'):
                    max_hours = int(filters['max_delivery_time'])
                    queryset = queryset.filter(
                        offers__delivery_time_hours__lte=max_hours,
                        offers__is_active=True
                    ).distinct()
                
                # Verified merchants only
                if filters.get('verified_only'):
                    queryset = queryset.filter(
                        offers__merchant__verified=True,
                        offers__is_active=True
                    ).distinct()
                
                # In stock only
                if filters.get('in_stock_only'):
                    queryset = queryset.filter(
                        offers__stock_quantity__gt=0,
                        offers__is_active=True
                    ).distinct()
            
            # Only products with active offers
            queryset = queryset.filter(offers__is_active=True).distinct()
            
            # Sorting
            if sort_by == 'price_low':
                queryset = queryset.annotate(
                    min_price=Min('offers__price')
                ).order_by('min_price')
            elif sort_by == 'price_high':
                queryset = queryset.annotate(
                    max_price=Max('offers__price')
                ).order_by('-max_price')
            elif sort_by == 'rating':
                queryset = queryset.annotate(
                    max_rating=Max('amazon_rating', 'flipkart_rating')
                ).order_by('-max_rating')
            elif sort_by == 'delivery_fast':
                queryset = queryset.annotate(
                    min_delivery=Min('offers__delivery_time_hours')
                ).order_by('min_delivery')
            elif sort_by == 'newest':
                queryset = queryset.order_by('-created_at')
            else:  # relevance
                if query:
                    # Enhanced relevance scoring
                    queryset = queryset.annotate(
                        relevance=Count(
                            Case(
                                When(name__iexact=query, then=3),
                                When(barcode__iexact=query, then=3),
                                When(name__icontains=query, then=2),
                                When(description__icontains=query, then=1),
                                default=0,
                                output_field=IntegerField()
                            )
                        )
                    ).order_by('-relevance', '-created_at')
                else:
                    queryset = queryset.order_by('-created_at')
            
            # Track search activity
            if user:
                UserActivity.objects.create(
                    user=user,
                    activity_type='advanced_search',
                    metadata={
                        'query': query,
                        'filters': filters or {},
                        'sort_by': sort_by,
                        'results_count': queryset.count()
                    }
                )
            
            return queryset
            
        except Exception as e:
            logger.error(f"Error in advanced search: {e}")
            return Product.objects.none()
