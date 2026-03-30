"""
AI-powered Merchant Services
Integrates AI features with merchant-specific operations
"""

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import Q, Count, Avg, Sum, Min, Max
from decimal import Decimal
import logging

from ..core.models import Product, Offer, Merchant, PriceHistory, UserActivity, PriceMatchRequest
from ..ai_engine.integrations import ai_integration

logger = logging.getLogger(__name__)

class MerchantAIService:
    """AI services for merchant-specific operations"""
    
    @staticmethod
    def get_pricing_suggestions(merchant, product_id=None):
        """
        Get AI-powered pricing suggestions for merchant
        """
        try:
            suggestions = {}
            
            if product_id:
                # Get pricing suggestions for specific product
                try:
                    product = Product.objects.get(id=product_id)
                    
                    # Get competitor prices
                    competitor_offers = Offer.objects.filter(
                        product=product
                    ).exclude(merchant=merchant).order_by('price')
                    
                    if competitor_offers.exists():
                        prices = [float(offer.price) for offer in competitor_offers]
                        avg_price = sum(prices) / len(prices)
                        min_price = min(prices)
                        max_price = max(prices)
                        
                        # AI pricing strategy
                        current_offer = Offer.objects.filter(
                            product=product,
                            merchant=merchant
                        ).first()
                        
                        current_price = float(current_offer.price) if current_offer else None
                        
                        suggestions[product_id] = {
                            'product': product,
                            'current_price': current_price,
                            'avg_competitor_price': avg_price,
                            'min_competitor_price': min_price,
                            'max_competitor_price': max_price,
                            'recommended_price': MerchantAIService._calculate_optimal_price(
                                current_price, avg_price, min_price, merchant
                            ),
                            'price_position': MerchantAIService._get_price_position(
                                current_price, prices
                            ) if current_price else None,
                            'competitor_count': len(prices),
                            'pricing_strategy': MerchantAIService._recommend_pricing_strategy(
                                current_price, avg_price, min_price
                            )
                        }
                
                except Product.DoesNotExist:
                    pass
            
            else:
                # Get general pricing suggestions for merchant's products
                merchant_products = Product.objects.filter(
                    offer__merchant=merchant
                ).distinct()
                
                for product in merchant_products[:20]:  # Limit to top 20 products
                    product_suggestions = MerchantAIService.get_pricing_suggestions(
                        merchant, product.id
                    )
                    if product_id in product_suggestions:
                        suggestions[product_id] = product_suggestions[product_id]
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Error getting pricing suggestions: {str(e)}")
            return {}
    
    @staticmethod
    def get_demand_forecast(merchant, days_ahead=30):
        """
        Get demand forecast for merchant's products
        """
        try:
            # Get merchant's products
            merchant_products = Product.objects.filter(
                offer__merchant=merchant
            ).distinct()
            
            forecasts = {}
            
            for product in merchant_products:
                # Get historical demand data
                historical_views = UserActivity.objects.filter(
                    product=product,
                    activity_type='product_view',
                    created_at__gte=timezone.now() - timedelta(days=90)
                ).count()
                
                historical_adds_to_cart = UserActivity.objects.filter(
                    product=product,
                    activity_type='add_to_cart',
                    created_at__gte=timezone.now() - timedelta(days=90)
                ).count()
                
                # Calculate demand metrics
                view_to_cart_ratio = historical_adds_to_cart / max(historical_views, 1)
                demand_score = historical_views + (historical_adds_to_cart * 2)
                
                # Get price trend influence
                price_history = PriceHistory.objects.filter(
                    product=product
                ).order_by('-created_at')[:30]
                
                price_trend_factor = 1.0
                if price_history.exists():
                    recent_prices = [float(ph.price) for ph in price_history[:7]]
                    older_prices = [float(ph.price) for ph in price_history[7:14]]
                    
                    if recent_prices and older_prices:
                        avg_recent = sum(recent_prices) / len(recent_prices)
                        avg_older = sum(older_prices) / len(older_prices)
                        price_trend_factor = avg_recent / avg_older if avg_older > 0 else 1.0
                
                # Seasonal adjustments (simplified)
                from datetime import datetime
                current_month = datetime.now().month
                seasonal_factor = MerchantAIService._get_seasonal_factor(product.category.name if product.category else 'General', current_month)
                
                # Calculate forecast
                base_demand = demand_score / 90  # Daily average
                forecasted_demand = base_demand * days_ahead * price_trend_factor * seasonal_factor
                
                forecasts[product.id] = {
                    'product': product,
                    'current_daily_demand': base_demand,
                    'forecasted_demand': forecasted_demand,
                    'demand_trend': 'increasing' if price_trend_factor > 1.05 else 'decreasing' if price_trend_factor < 0.95 else 'stable',
                    'seasonal_factor': seasonal_factor,
                    'confidence': min(0.9, historical_views / 100),  # Higher confidence with more data
                    'recommendations': MerchantAIService._generate_demand_recommendations(
                        forecasted_demand, base_demand, product
                    )
                }
            
            return forecasts
            
        except Exception as e:
            logger.error(f"Error getting demand forecast: {str(e)}")
            return {}
    
    @staticmethod
    def get_competitor_analysis(merchant, category=None):
        """
        Get competitor analysis for merchant
        """
        try:
            # Get competitors in same category/location
            competitors_query = Merchant.objects.filter(
                verified=True
            ).exclude(id=merchant.id)
            
            if category:
                competitors_query = competitors_query.filter(
                    offer__product__category__name=category
                ).distinct()
            
            competitors = competitors_query[:10]  # Top 10 competitors
            
            analysis = {}
            
            for competitor in competitors:
                # Get competitor's performance metrics
                competitor_offers = Offer.objects.filter(merchant=competitor)
                
                if competitor_offers.exists():
                    avg_price = competitor_offers.aggregate(
                        avg_price=Avg('price')
                    )['avg_price'] or 0
                    
                    avg_discount = competitor_offers.aggregate(
                        avg_discount=Avg('discount_percentage')
                    )['avg_discount'] or 0
                    
                    total_products = competitor_offers.values('product').distinct().count()
                    
                    # Get competitor's rating and reviews
                    avg_rating = competitor.rating or 0
                    
                    analysis[competitor.id] = {
                        'competitor': competitor,
                        'total_products': total_products,
                        'avg_price': float(avg_price),
                        'avg_discount': float(avg_discount),
                        'rating': float(avg_rating),
                        'price_competitiveness': MerchantAIService._calculate_price_competitiveness(
                            avg_price, avg_discount
                        ),
                        'market_position': MerchantAIService._calculate_market_position(
                            avg_price, avg_discount, avg_rating
                        )
                    }
            
            # Sort competitors by market position
            sorted_competitors = sorted(
                analysis.items(),
                key=lambda x: x[1]['market_position'],
                reverse=True
            )
            
            return {
                'competitors': dict(sorted_competitors),
                'merchant_position': MerchantAIService._get_merchant_position(merchant, analysis),
                'market_insights': MerchantAIService._generate_market_insights(analysis)
            }
            
        except Exception as e:
            logger.error(f"Error getting competitor analysis: {str(e)}")
            return {}
    
    @staticmethod
    def optimize_inventory(merchant):
        """
        Optimize merchant's inventory using AI
        """
        try:
            # Get merchant's current inventory
            merchant_offers = Offer.objects.filter(
                merchant=merchant
            ).select_related('product', 'product__category')
            
            optimization_suggestions = []
            
            for offer in merchant_offers:
                product = offer.product
                
                # Get demand forecast for this product
                forecasts = MerchantAIService.get_demand_forecast(merchant, days_ahead=30)
                product_forecast = forecasts.get(product.id, {})
                
                if not product_forecast:
                    continue
                
                # Get current stock and sales velocity
                current_stock = offer.stock_quantity or 100
                daily_demand = product_forecast.get('current_daily_demand', 0)
                
                # Calculate days of inventory
                days_of_inventory = current_stock / max(daily_demand, 1)
                
                # Generate inventory recommendations
                if days_of_inventory < 7:
                    # Low stock - recommend restock
                    optimization_suggestions.append({
                        'type': 'restock',
                        'product': product,
                        'current_stock': current_stock,
                        'recommended_stock': int(daily_demand * 30),  # 30 days supply
                        'urgency': 'high',
                        'reason': f'Only {days_of_inventory:.1f} days of inventory left'
                    })
                elif days_of_inventory > 90:
                    # Overstock - recommend promotion
                    optimization_suggestions.append({
                        'type': 'promotion',
                        'product': product,
                        'current_stock': current_stock,
                        'recommended_discount': 15,  # 15% discount
                        'urgency': 'medium',
                        'reason': f'{days_of_inventory:.1f} days of inventory - consider promotion'
                    })
                
                # Price optimization
                pricing_suggestions = MerchantAIService.get_pricing_suggestions(merchant, product.id)
                if product.id in pricing_suggestions:
                    pricing = pricing_suggestions[product.id]
                    if pricing.get('pricing_strategy') == 'reduce_price':
                        optimization_suggestions.append({
                            'type': 'price_adjustment',
                            'product': product,
                            'current_price': pricing['current_price'],
                            'recommended_price': pricing['recommended_price'],
                            'urgency': 'medium',
                            'reason': 'Price above market average'
                        })
            
            # Sort suggestions by urgency
            urgency_order = {'high': 3, 'medium': 2, 'low': 1}
            optimization_suggestions.sort(
                key=lambda x: urgency_order.get(x['urgency'], 0),
                reverse=True
            )
            
            return {
                'total_products': len(merchant_offers),
                'optimization_suggestions': optimization_suggestions,
                'summary': {
                    'low_stock_items': len([s for s in optimization_suggestions if s['type'] == 'restock']),
                    'overstock_items': len([s for s in optimization_suggestions if s['type'] == 'promotion']),
                    'price_adjustment_items': len([s for s in optimization_suggestions if s['type'] == 'price_adjustment'])
                }
            }
            
        except Exception as e:
            logger.error(f"Error optimizing inventory: {str(e)}")
            return {
                'total_products': 0,
                'optimization_suggestions': [],
                'summary': {
                    'low_stock_items': 0,
                    'overstock_items': 0,
                    'price_adjustment_items': 0
                }
            }
    
    @staticmethod
    def get_performance_insights(merchant, days=30):
        """
        Get AI-powered performance insights for merchant
        """
        try:
            from datetime import timedelta
            from django.utils import timezone
            
            # Get date range
            end_date = timezone.now()
            start_date = end_date - timedelta(days=days)
            
            # Get merchant's offers in the period
            offers = Offer.objects.filter(
                merchant=merchant,
                created_at__gte=start_date,
                created_at__lte=end_date
            ).select_related('product')
            
            # Get user interactions
            product_ids = offers.values_list('product__id', flat=True)
            interactions = UserActivity.objects.filter(
                product__id__in=product_ids,
                created_at__gte=start_date,
                created_at__lte=end_date
            )
            
            # Calculate metrics
            total_views = interactions.filter(activity_type='product_view').count()
            total_cart_adds = interactions.filter(activity_type='add_to_cart').count()
            total_searches = interactions.filter(activity_type='search').count()
            
            # Calculate conversion rates
            view_to_cart_rate = total_cart_adds / max(total_views, 1)
            search_to_view_rate = total_views / max(total_searches, 1)
            
            # Get price match requests
            price_matches = PriceMatchRequest.objects.filter(
                merchant=merchant,
                created_at__gte=start_date
            )
            
            total_price_matches = price_matches.count()
            accepted_price_matches = price_matches.filter(status='accepted').count()
            price_match_acceptance_rate = accepted_price_matches / max(total_price_matches, 1)
            
            # Get performance trends
            insights = {
                'period_days': days,
                'total_products': len(offers),
                'total_views': total_views,
                'total_cart_adds': total_cart_adds,
                'total_searches': total_searches,
                'view_to_cart_rate': view_to_cart_rate,
                'search_to_view_rate': search_to_view_rate,
                'total_price_matches': total_price_matches,
                'accepted_price_matches': accepted_price_matches,
                'price_match_acceptance_rate': price_match_acceptance_rate,
                'performance_score': MerchantAIService._calculate_performance_score(
                    view_to_cart_rate, price_match_acceptance_rate, len(offers)
                ),
                'recommendations': MerchantAIService._generate_performance_recommendations(
                    view_to_cart_rate, price_match_acceptance_rate, len(offers)
                )
            }
            
            return insights
            
        except Exception as e:
            logger.error(f"Error getting performance insights: {str(e)}")
            return {}
    
    # Helper methods
    @staticmethod
    def _calculate_optimal_price(current_price, avg_competitor_price, min_competitor_price, merchant):
        """Calculate optimal price based on competition"""
        if not current_price:
            # No current price, recommend competitive pricing
            return min_competitor_price * 0.95  # 5% below minimum
        
        # Price positioning strategy
        merchant_rating = merchant.rating or 4.0
        
        if merchant_rating >= 4.5:
            # High-rated merchant can price higher
            return min_competitor_price * 1.05  # 5% above minimum
        elif merchant_rating >= 3.5:
            # Average-rated merchant should be competitive
            return avg_competitor_price * 0.98  # 2% below average
        else:
            # Lower-rated merchant should be price competitive
            return min_competitor_price * 0.92  # 8% below minimum
    
    @staticmethod
    def _get_price_position(current_price, competitor_prices):
        """Get price position relative to competitors"""
        if not current_price:
            return None
        
        prices_sorted = sorted(competitor_prices + [current_price])
        position = prices_sorted.index(current_price) + 1
        total = len(prices_sorted)
        
        percentile = (total - position) / total * 100
        return {
            'position': position,
            'total': total,
            'percentile': percentile,
            'label': 'lowest' if percentile >= 90 else 'competitive' if percentile >= 50 else 'expensive'
        }
    
    @staticmethod
    def _recommend_pricing_strategy(current_price, avg_price, min_price):
        """Recommend pricing strategy"""
        if not current_price:
            return 'new_listing'
        
        price_gap_to_min = ((current_price - min_price) / min_price * 100) if min_price > 0 else 0
        price_gap_to_avg = ((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0
        
        if price_gap_to_min > 20:
            return 'reduce_price'
        elif price_gap_to_min < -10:
            return 'increase_price'
        elif price_gap_to_avg > 15:
            return 'match_competition'
        else:
            return 'maintain_price'
    
    @staticmethod
    def _get_seasonal_factor(category, month):
        """Get seasonal demand factor for category and month"""
        seasonal_factors = {
            'Electronics': {
                1: 1.2, 2: 1.1, 3: 0.9, 4: 0.8, 5: 0.7, 6: 0.6,
                7: 0.5, 8: 0.6, 9: 0.8, 10: 1.0, 11: 1.3, 12: 1.4
            },
            'Clothing': {
                1: 0.6, 2: 0.7, 3: 0.9, 4: 1.2, 5: 1.3, 6: 1.2,
                7: 0.8, 8: 0.7, 9: 0.9, 10: 1.1, 11: 1.2, 12: 1.3
            },
            'Home': {
                1: 0.8, 2: 0.9, 3: 1.0, 4: 1.1, 5: 1.0, 6: 0.9,
                7: 0.8, 8: 0.9, 9: 1.0, 10: 1.1, 11: 1.0, 12: 0.9
            }
        }
        
        return seasonal_factors.get(category, {}).get(month, 1.0)
    
    @staticmethod
    def _generate_demand_recommendations(forecasted_demand, current_demand, product):
        """Generate demand-based recommendations"""
        recommendations = []
        
        if forecasted_demand > current_demand * 1.5:
            recommendations.append({
                'type': 'increase_stock',
                'message': f'Demand expected to increase by {((forecasted_demand/current_demand - 1) * 100):.1f}%'
            })
        elif forecasted_demand < current_demand * 0.7:
            recommendations.append({
                'type': 'reduce_stock',
                'message': f'Demand expected to decrease by {((1 - forecasted_demand/current_demand) * 100):.1f}%'
            })
        
        return recommendations
    
    @staticmethod
    def _calculate_price_competitiveness(avg_price, avg_discount):
        """Calculate price competitiveness score"""
        # Higher discount and lower price = more competitive
        price_score = max(0, (1000 - avg_price) / 1000)  # Normalize price
        discount_score = avg_discount / 50  # Normalize discount (max 50%)
        
        return (price_score + discount_score) / 2
    
    @staticmethod
    def _calculate_market_position(avg_price, avg_discount, avg_rating):
        """Calculate overall market position score"""
        # Weighted score: price (40%), discount (30%), rating (30%)
        price_score = max(0, (1000 - avg_price) / 1000)
        discount_score = avg_discount / 50
        rating_score = avg_rating / 5
        
        return (price_score * 0.4) + (discount_score * 0.3) + (rating_score * 0.3)
    
    @staticmethod
    def _get_merchant_position(merchant, competitor_analysis):
        """Get merchant's position relative to competitors"""
        # Get merchant's metrics
        merchant_offers = Offer.objects.filter(merchant=merchant)
        
        if not merchant_offers.exists():
            return 'no_data'
        
        avg_price = merchant_offers.aggregate(avg_price=Avg('price'))['avg_price'] or 0
        avg_discount = merchant_offers.aggregate(avg_discount=Avg('discount_percentage'))['avg_discount'] or 0
        avg_rating = merchant.rating or 0
        
        merchant_score = MerchantAIService._calculate_market_position(avg_price, avg_discount, avg_rating)
        
        # Compare with competitors
        competitor_scores = [
            data['market_position'] for data in competitor_analysis.values()
        ]
        
        if not competitor_scores:
            return 'leader'
        
        percentile = len([s for s in competitor_scores if s < merchant_score]) / len(competitor_scores) * 100
        
        if percentile >= 80:
            return 'leader'
        elif percentile >= 60:
            return 'competitive'
        elif percentile >= 40:
            return 'follower'
        else:
            return 'laggard'
    
    @staticmethod
    def _generate_market_insights(competitor_analysis):
        """Generate market insights from competitor analysis"""
        if not competitor_analysis:
            return {}
        
        # Calculate market averages
        all_prices = [data['avg_price'] for data in competitor_analysis.values()]
        all_discounts = [data['avg_discount'] for data in competitor_analysis.values()]
        all_ratings = [data['rating'] for data in competitor_analysis.values()]
        
        return {
            'market_avg_price': sum(all_prices) / len(all_prices) if all_prices else 0,
            'market_avg_discount': sum(all_discounts) / len(all_discounts) if all_discounts else 0,
            'market_avg_rating': sum(all_ratings) / len(all_ratings) if all_ratings else 0,
            'price_range': {'min': min(all_prices), 'max': max(all_prices)} if all_prices else {},
            'discount_range': {'min': min(all_discounts), 'max': max(all_discounts)} if all_discounts else {},
            'total_competitors': len(competitor_analysis)
        }
    
    @staticmethod
    def _calculate_performance_score(view_to_cart_rate, price_match_acceptance_rate, total_products):
        """Calculate overall performance score"""
        # Weighted score: conversion (40%), price match (30%), product variety (30%)
        conversion_score = min(view_to_cart_rate * 10, 1.0)  # Normalize to 0-1
        price_match_score = price_match_acceptance_rate
        variety_score = min(total_products / 100, 1.0)  # Normalize (100 products = perfect)
        
        return (conversion_score * 0.4) + (price_match_score * 0.3) + (variety_score * 0.3)
    
    @staticmethod
    def _generate_performance_recommendations(view_to_cart_rate, price_match_acceptance_rate, total_products):
        """Generate performance improvement recommendations"""
        recommendations = []
        
        if view_to_cart_rate < 0.05:  # Less than 5% conversion
            recommendations.append({
                'type': 'improve_listings',
                'message': 'Low conversion rate. Improve product photos and descriptions.',
                'priority': 'high'
            })
        
        if price_match_acceptance_rate < 0.5:  # Less than 50% acceptance
            recommendations.append({
                'type': 'review_pricing',
                'message': 'Low price match acceptance. Consider more competitive pricing.',
                'priority': 'medium'
            })
        
        if total_products < 20:
            recommendations.append({
                'type': 'expand_catalog',
                'message': 'Limited product variety. Add more products to attract customers.',
                'priority': 'low'
            })
        
        return recommendations
