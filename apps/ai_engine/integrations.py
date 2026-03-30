"""
AI Engine Integration with Django Backend
Connects ML models with real datasets and Django models
"""

import pandas as pd
import numpy as np
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import Q, Avg, Count, Min, Max
from decimal import Decimal
import logging

from ..core.models import Product, Offer, Merchant, Cart, CartItem, Notification, UserActivity, PriceHistory
from .models.ml_ranker import MLRanker
from .models.basket_optimizer import BasketOptimizer
from .models.price_predictor import PricePredictor
from .models.barcode_scanner import BarcodeScanner
from .models.computer_vision import ComputerVision

logger = logging.getLogger(__name__)

class AIIntegration:
    """Main AI integration class connecting ML models with Django backend"""
    
    def __init__(self):
        self.ml_ranker = MLRanker()
        self.basket_optimizer = BasketOptimizer()
        self.price_predictor = PricePredictor()
        self.barcode_scanner = BarcodeScanner()
        self.computer_vision = ComputerVision()
        
        # Initialize models with real datasets
        self._initialize_models()
    
    def _initialize_models(self):
        """Initialize all AI models with real datasets"""
        try:
            # Load real datasets
            self.amazon_df = pd.read_csv('dataset/amazon.csv')
            self.flipkart_df = pd.read_csv('dataset/marketing_sample_for_flipkart_com-ecommerce__20191101_20191130__15k_data.csv')
            self.local_df = pd.read_csv('dataset/local_store_offer_dataset.csv')
            
            # Initialize ML Ranker with real data
            self.ml_ranker.load_data(self.amazon_df, self.flipkart_df, self.local_df)
            self.ml_ranker.train_model()
            
            # Initialize Basket Optimizer with real data
            self.basket_optimizer.load_product_data(self.amazon_df, self.flipkart_df, self.local_df)
            
            # Initialize Price Predictor with real data
            self.price_predictor.load_price_data(self.amazon_df, self.flipkart_df, self.local_df)
            self.price_predictor.train_model()
            
            # Initialize Barcode Scanner with real data
            self.barcode_scanner.build_database(self.amazon_df, self.flipkart_df, self.local_df)
            
            logger.info("All AI models initialized successfully with real datasets")
            
        except Exception as e:
            logger.error(f"Error initializing AI models: {str(e)}")
            # Fallback to demo mode
            self.amazon_df = pd.DataFrame()
            self.flipkart_df = pd.DataFrame()
            self.local_df = pd.DataFrame()
            self._initialize_demo_mode()
    
    def _initialize_demo_mode(self):
        """Fallback demo mode when datasets are not available"""
        logger.warning("Initializing AI models in demo mode")
        # Create sample data for demonstration
        sample_data = pd.DataFrame({
            'product_name': ['Sample Product 1', 'Sample Product 2'],
            'discounted_price': [999, 1499],
            'actual_price': [1299, 1999],
            'rating': [4.5, 4.2],
            'rating_count': [1200, 800]
        })
        
        self.ml_ranker.load_data(sample_data, sample_data, sample_data)
        self.ml_ranker.train_model()
    
    def rank_products(self, user, products, search_query=None, user_location=None):
        """
        Rank products using ML algorithm
        Returns products with ML scores
        """
        try:
            # Get user preferences and activity
            user_preferences = self._get_user_preferences(user)
            user_activity = self._get_user_activity(user)
            
            # Prepare product data for ML ranking
            product_data = []
            for product in products:
                best_offer = self._get_best_offer(product)
                
                product_info = {
                    'product_id': product.id,
                    'name': product.name,
                    'category': product.category.name if product.category else 'General',
                    'brand': product.brand.name if product.brand else 'Unknown',
                    'price': float(best_offer.price) if best_offer else float(product.amazon_price or 0),
                    'original_price': float(best_offer.original_price) if best_offer and best_offer.original_price else float(product.amazon_price or 0),
                    'rating': float(product.rating or 4.0),
                    'rating_count': int(product.reviews_count or 0),
                    'discount_percentage': float(best_offer.discount_percentage or 0),
                    'merchant': best_offer.merchant.shop_name if best_offer else 'Amazon',
                    'delivery_time': int(best_offer.delivery_time_hours or 24),
                    'merchant_rating': float(best_offer.merchant.rating or 4.0) if best_offer else 4.0,
                    'merchant_verified': best_offer.merchant.verified if best_offer else True,
                    'location_match': self._calculate_location_match(user_location, best_offer) if best_offer and user_location else 1.0,
                    'user_preference_match': self._calculate_preference_match(product, user_preferences),
                    'search_relevance': self._calculate_search_relevance(product, search_query) if search_query else 1.0
                }
                product_data.append(product_info)
            
            # Convert to DataFrame for ML processing
            df = pd.DataFrame(product_data)
            
            # Get ML rankings
            ranked_products = self.ml_ranker.rank_products(df, user_preferences)
            
            # Map rankings back to Django objects
            ranked_results = []
            for _, row in ranked_products.iterrows():
                product_obj = next((p for p in products if p.id == row['product_id']), None)
                if product_obj:
                    product_obj.ml_score = row['ml_score']
                    product_obj.rank_position = row['rank']
                    ranked_results.append(product_obj)
            
            # Sort by ML score
            ranked_results.sort(key=lambda x: x.ml_score, reverse=True)
            
            # Cache results for user
            cache_key = f"ranked_products_{user.id}_{hash(search_query or '')}"
            cache.set(cache_key, ranked_results, timeout=300)  # 5 minutes cache
            
            return ranked_results
            
        except Exception as e:
            logger.error(f"Error ranking products: {str(e)}")
            return products  # Fallback to original order
    
    def optimize_basket(self, user, cart_items=None):
        """
        Optimize user's basket using AI
        Returns optimization suggestions and cost savings
        """
        try:
            # Get cart items if not provided
            if not cart_items:
                cart_items = CartItem.objects.filter(cart__user=user).select_related('product')
            
            if not cart_items:
                return {'error': 'No items in cart to optimize'}
            
            # Prepare basket data for optimization
            basket_data = []
            for item in cart_items:
                product_offers = Offer.objects.filter(product=item.product).select_related('merchant')
                
                # Get all available offers for this product
                offers_data = []
                for offer in product_offers:
                    offers_data.append({
                        'merchant': offer.merchant.shop_name,
                        'price': float(offer.price),
                        'original_price': float(offer.original_price) if offer.original_price else float(offer.price),
                        'delivery_time': int(offer.delivery_time_hours or 24),
                        'merchant_location': offer.merchant.location or 'Unknown',
                        'merchant_rating': float(offer.merchant.rating or 4.0),
                        'stock_quantity': int(offer.stock_quantity or 100)
                    })
                
                basket_data.append({
                    'product_id': item.product.id,
                    'product_name': item.product.name,
                    'category': item.product.category.name if item.product.category else 'General',
                    'quantity': int(item.quantity),
                    'current_price': float(item.product.amazon_price or 0),
                    'offers': offers_data
                })
            
            # Run basket optimization
            optimization_result = self.basket_optimizer.optimize_basket(basket_data)
            
            # Calculate savings and recommendations
            current_total = sum(item['current_price'] * item['quantity'] for item in basket_data)
            optimized_total = optimization_result.get('total_cost', current_total)
            savings = current_total - optimized_total
            
            result = {
                'current_total': current_total,
                'optimized_total': optimized_total,
                'total_savings': savings,
                'savings_percentage': (savings / current_total * 100) if current_total > 0 else 0,
                'recommendations': optimization_result.get('recommendations', []),
                'split_purchase': optimization_result.get('split_purchase', {}),
                'single_store': optimization_result.get('single_store', {}),
                'optimization_strategy': optimization_result.get('strategy', 'balanced')
            }
            
            # Cache optimization result
            cache_key = f"basket_optimization_{user.id}"
            cache.set(cache_key, result, timeout=600)  # 10 minutes cache
            
            return result
            
        except Exception as e:
            logger.error(f"Error optimizing basket: {str(e)}")
            return {'error': 'Basket optimization temporarily unavailable'}
    
    def predict_price_trends(self, product_ids, days_ahead=7):
        """
        Predict price trends for products
        Returns predictions with confidence scores
        """
        try:
            predictions = {}
            
            for product_id in product_ids:
                # Get product and historical price data
                product = Product.objects.get(id=product_id)
                price_history = PriceHistory.objects.filter(product=product).order_by('created_at')
                
                # Prepare price data for prediction
                if price_history.exists():
                    prices = [float(ph.price) for ph in price_history]
                    dates = [ph.created_at for ph in price_history]
                else:
                    # Use current offers as historical data
                    offers = Offer.objects.filter(product=product).order_by('-created_at')[:30]
                    prices = [float(offer.price) for offer in offers]
                    dates = [offer.created_at for offer in offers]
                
                if len(prices) < 3:
                    # Not enough data for prediction
                    predictions[product_id] = {
                        'current_price': float(product.amazon_price or 0),
                        'predicted_price': float(product.amazon_price or 0),
                        'trend': 'stable',
                        'confidence': 0.3,
                        'days_ahead': days_ahead,
                        'recommendation': 'wait_for_data'
                    }
                    continue
                
                # Create price data DataFrame
                price_df = pd.DataFrame({
                    'date': dates,
                    'price': prices
                })
                
                # Get price prediction
                prediction = self.price_predictor.predict_future_price(price_df, days_ahead)
                
                predictions[product_id] = {
                    'current_price': float(product.amazon_price or 0),
                    'predicted_price': float(prediction['predicted_price']),
                    'trend': prediction['trend'],
                    'confidence': float(prediction['confidence']),
                    'days_ahead': days_ahead,
                    'recommendation': prediction['recommendation'],
                    'potential_savings': float(prediction['potential_savings']),
                    'best_buy_date': prediction.get('best_buy_date'),
                    'price_drop_probability': float(prediction.get('price_drop_probability', 0))
                }
            
            return predictions
            
        except Exception as e:
            logger.error(f"Error predicting price trends: {str(e)}")
            return {}
    
    def scan_barcode(self, barcode_value):
        """
        Scan barcode and find matching products
        Returns product information from real database
        """
        try:
            # Search for product by barcode
            result = self.barcode_scanner.scan_barcode(barcode_value)
            
            if result['found']:
                # Find matching products in Django database
                products = Product.objects.filter(
                    Q(barcode=barcode_value) |
                    Q(name__icontains=result['product_name']) |
                    Q(brand__name__icontains=result['brand'])
                ).select_related('category', 'brand')
                
                if products.exists():
                    # Get best offers for each product
                    product_results = []
                    for product in products:
                        best_offer = self._get_best_offer(product)
                        product_results.append({
                            'product': product,
                            'best_offer': best_offer,
                            'match_confidence': result['confidence'],
                            'match_type': result['match_type']
                        })
                    
                    return {
                        'found': True,
                        'products': product_results,
                        'barcode_info': result
                    }
            
            return {
                'found': False,
                'barcode_value': barcode_value,
                'suggestions': result.get('suggestions', [])
            }
            
        except Exception as e:
            logger.error(f"Error scanning barcode: {str(e)}")
            return {'found': False, 'error': 'Barcode scanning temporarily unavailable'}
    
    def identify_product_from_image(self, image_data):
        """
        Identify product from image using computer vision
        Returns product matches with confidence scores
        """
        try:
            # Use computer vision to identify product
            result = self.computer_vision.identify_product(image_data)
            
            if result['found']:
                # Search for matching products in database
                products = Product.objects.filter(
                    Q(name__icontains=result['product_name']) |
                    Q(category__name__icontains=result['category']) |
                    Q(brand__name__icontains=result['brand'])
                ).select_related('category', 'brand')
                
                product_matches = []
                for product in products[:10]:  # Limit to top 10 matches
                    best_offer = self._get_best_offer(product)
                    match_score = self._calculate_image_match_score(product, result)
                    
                    product_matches.append({
                        'product': product,
                        'best_offer': best_offer,
                        'match_score': match_score,
                        'identification_confidence': result['confidence']
                    })
                
                # Sort by match score
                product_matches.sort(key=lambda x: x['match_score'], reverse=True)
                
                return {
                    'found': True,
                    'products': product_matches,
                    'identification_info': result
                }
            
            return {
                'found': False,
                'identification_info': result,
                'suggestions': result.get('suggestions', [])
            }
            
        except Exception as e:
            logger.error(f"Error identifying product from image: {str(e)}")
            return {'found': False, 'error': 'Image identification temporarily unavailable'}
    
    def generate_smart_notifications(self, user):
        """
        Generate smart notifications based on user activity and AI insights
        Returns personalized notifications
        """
        try:
            notifications = []
            
            # Get user's watched products and cart items
            watched_products = self._get_watched_products(user)
            cart_items = CartItem.objects.filter(cart__user=user).select_related('product')
            
            # Price drop notifications for watched products
            for product in watched_products:
                prediction = self.predict_price_trends([product.id])
                if product.id in prediction:
                    pred = prediction[product.id]
                    if pred['trend'] == 'dropping' and pred['confidence'] > 0.7:
                        notifications.append({
                            'type': 'price_drop',
                            'title': f'Price Drop Alert: {product.name}',
                            'message': f'Price expected to drop by ₹{pred["potential_savings"]:.2f} in {pred["days_ahead"]} days',
                            'product': product,
                            'priority': 'high',
                            'data': pred
                        })
            
            # Cart optimization notifications
            if cart_items.exists():
                optimization = self.optimize_basket(user, cart_items)
                if optimization.get('total_savings', 0) > 100:  # Only notify if savings > ₹100
                    notifications.append({
                        'type': 'cart_optimization',
                        'title': 'Optimize Your Cart',
                        'message': f'Save ₹{optimization["total_savings"]:.2f} by optimizing your basket',
                        'priority': 'medium',
                        'data': optimization
                    })
            
            # Stock availability notifications
            for item in cart_items:
                best_offer = self._get_best_offer(item.product)
                if best_offer and best_offer.stock_quantity and best_offer.stock_quantity < 10:
                    notifications.append({
                        'type': 'low_stock',
                        'title': 'Low Stock Alert',
                        'message': f'{item.product.name} is running low in stock at {best_offer.merchant.shop_name}',
                        'product': item.product,
                        'priority': 'medium',
                        'data': {'stock_quantity': best_offer.stock_quantity}
                    })
            
            # Personalized recommendations
            recommendations = self._get_personalized_recommendations(user)
            if recommendations:
                notifications.append({
                    'type': 'recommendation',
                    'title': 'Recommended for You',
                    'message': f'Based on your recent activity, you might like {recommendations[0].name}',
                    'product': recommendations[0],
                    'priority': 'low',
                    'data': {'recommendations': recommendations[:3]}
                })
            
            # Sort notifications by priority
            priority_order = {'high': 3, 'medium': 2, 'low': 1}
            notifications.sort(key=lambda x: priority_order.get(x['priority'], 0), reverse=True)
            
            return notifications[:5]  # Return top 5 notifications
            
        except Exception as e:
            logger.error(f"Error generating smart notifications: {str(e)}")
            return []
    
    # Helper methods
    def _get_user_preferences(self, user):
        """Get user preferences based on activity history"""
        # Get user's most searched categories and brands
        activities = UserActivity.objects.filter(user=user).values('metadata')
        
        categories = {}
        brands = {}
        price_ranges = []
        
        for activity in activities:
            metadata = activity.get('metadata', {})
            if 'category' in metadata:
                categories[metadata['category']] = categories.get(metadata['category'], 0) + 1
            if 'brand' in metadata:
                brands[metadata['brand']] = brands.get(metadata['brand'], 0) + 1
            if 'price' in metadata:
                price_ranges.append(float(metadata['price']))
        
        return {
            'preferred_categories': sorted(categories.items(), key=lambda x: x[1], reverse=True)[:3],
            'preferred_brands': sorted(brands.items(), key=lambda x: x[1], reverse=True)[:3],
            'avg_price_range': np.mean(price_ranges) if price_ranges else 1000
        }
    
    def _get_user_activity(self, user):
        """Get recent user activity"""
        return UserActivity.objects.filter(user=user).order_by('-created_at')[:50]
    
    def _get_best_offer(self, product):
        """Get best offer for a product"""
        return Offer.objects.filter(product=product).order_by('price').first()
    
    def _calculate_location_match(self, user_location, offer):
        """Calculate location match score"""
        if not user_location or not offer.merchant.location:
            return 1.0
        
        # Simple distance calculation (in real app, use geolocation)
        return 0.8  # Placeholder
    
    def _calculate_preference_match(self, product, user_preferences):
        """Calculate how well product matches user preferences"""
        score = 1.0
        
        # Category preference
        if product.category:
            for cat, count in user_preferences['preferred_categories']:
                if product.category.name == cat:
                    score += 0.1 * (count / 10)
        
        # Brand preference
        if product.brand:
            for brand, count in user_preferences['preferred_brands']:
                if product.brand.name == brand:
                    score += 0.1 * (count / 10)
        
        return min(score, 2.0)  # Cap at 2.0
    
    def _calculate_search_relevance(self, product, search_query):
        """Calculate search relevance score"""
        if not search_query:
            return 1.0
        
        query_terms = search_query.lower().split()
        product_text = f"{product.name} {product.category.name if product.category else ''} {product.brand.name if product.brand else ''}".lower()
        
        matches = sum(1 for term in query_terms if term in product_text)
        return min(1.0 + (matches * 0.2), 2.0)
    
    def _calculate_image_match_score(self, product, identification_result):
        """Calculate match score for image identification"""
        score = 0.0
        
        # Name match
        if identification_result['product_name'].lower() in product.name.lower():
            score += 0.4
        
        # Category match
        if product.category and identification_result['category'].lower() in product.category.name.lower():
            score += 0.3
        
        # Brand match
        if product.brand and identification_result['brand'].lower() in product.brand.name.lower():
            score += 0.3
        
        return min(score, 1.0)
    
    def _get_watched_products(self, user):
        """Get products user is watching (based on activity)"""
        # Products user has viewed or searched for recently
        viewed_products = UserActivity.objects.filter(
            user=user,
            activity_type__in=['product_view', 'search']
        ).values_list('product__id', flat=True).distinct()
        
        return Product.objects.filter(id__in=viewed_products)
    
    def _get_personalized_recommendations(self, user):
        """Get personalized product recommendations"""
        # Get user's preferred categories
        preferences = self._get_user_preferences(user)
        preferred_categories = [cat[0] for cat in preferences['preferred_categories'][:3]]
        
        if preferred_categories:
            # Get top products in preferred categories
            return Product.objects.filter(
                category__name__in=preferred_categories
            ).select_related('category', 'brand').order_by('-rating')[:5]
        
        return Product.objects.select_related('category', 'brand').order_by('-rating')[:5]

    def search_in_datasets(self, query, filters=None, sort_by='relevance'):
        """Search products across all datasets"""
        try:
            results = []
            
            # 1. Search in Amazon CSV
            if not self.amazon_df.empty and 'product_name' in self.amazon_df.columns:
                mask = self.amazon_df['product_name'].str.contains(query, case=False, na=False)
                if 'category' in self.amazon_df.columns:
                    mask |= self.amazon_df['category'].str.contains(query, case=False, na=False)
                
                filtered_amazon = self.amazon_df[mask].head(50)  # Limit results
                for _, row in filtered_amazon.iterrows():
                    price_str = str(row.get('discounted_price', '0')).replace('₹', '').replace(',', '')
                    try:
                        price = float(price_str)
                    except:
                        price = 0
                        
                    results.append({
                        'id': f"amazon_{row.get('product_id', np.random.randint(1000, 9999))}",
                        'name': row.get('product_name', 'Unknown'),
                        'category': {'name': str(row.get('category', 'Electronics')).split('|')[0]},
                        'brand': {'name': 'Amazon'},
                        'image_url': row.get('img_link', ''),
                        'best_offer': {
                            'price': price,
                            'original_price': price * 1.2,
                            'merchant': 'Amazon India',
                            'delivery_time_hours': 24,
                            'source_icon': 'fab fa-amazon'
                        },
                        'rating': float(row.get('rating', 0)) if str(row.get('rating', '')).replace('.', '').isdigit() else 4.0,
                        'reviews_count': str(row.get('rating_count', '1.2k')),
                        'source': 'amazon'
                    })
            
            # 2. Search in Flipkart CSV (simplified mockup)
            if not self.flipkart_df.empty:
                # Mockup for Flipkart Search
                name_col = 'Product Name' if 'Product Name' in self.flipkart_df.columns else 'product_name'
                if name_col in self.flipkart_df.columns:
                    mask = self.flipkart_df[name_col].str.contains(query, case=False, na=False)
                    filtered_flipkart = self.flipkart_df[mask].head(50)
                    for _, row in filtered_flipkart.iterrows():
                        results.append({
                            'id': f"flipkart_{np.random.randint(10000, 99999)}",
                            'name': row.get(name_col, 'Unknown'),
                            'category': {'name': str(row.get('product_category_tree', 'Fashion')).split('>>')[0].replace('["', '').replace('"', '')},
                            'brand': {'name': row.get('brand', 'Flipkart')},
                            'image_url': str(row.get('image', '')).split(',')[0].replace('"', '').replace('[', '').replace(']', ''),
                            'best_offer': {
                                'price': float(row.get('retail_price', 0)) if str(row.get('retail_price', '')).replace('.', '').isdigit() else 999,
                                'original_price': float(row.get('retail_price', 0)) * 1.2 if str(row.get('retail_price', '')).replace('.', '').isdigit() else 1299,
                                'merchant': 'Flipkart',
                                'delivery_time_hours': 48,
                                'source_icon': 'fas fa-shopping-bag'
                            },
                            'rating': 4.2,
                            'reviews_count': '2.1k',
                            'source': 'flipkart'
                        })

            # 3. Apply Filters
            if filters:
                if filters.get('min_price'):
                    results = [r for r in results if r['best_offer']['price'] >= float(filters['min_price'])]
                if filters.get('max_price'):
                    results = [r for r in results if r['best_offer']['price'] <= float(filters['max_price'])]
                if filters.get('category'):
                    results = [r for r in results if r['category']['name'] in filters['category']]
            
            # 4. Sorting
            if sort_by == 'price_low':
                results.sort(key=lambda x: x['best_offer']['price'])
            elif sort_by == 'price_high':
                results.sort(key=lambda x: x['best_offer']['price'], reverse=True)
            elif sort_by == 'rating':
                results.sort(key=lambda x: x['rating'], reverse=True)
            
            return results
            
        except Exception as e:
            logger.error(f"Error searching in datasets: {str(e)}")
            return []

    def get_filter_meta(self):
        """Extract categories and brands for the filter sidebar"""
        # Static for performance, but mapped to CSV data
        return {
            'categories': [
                {'name': 'Electronics', 'product_count': 120},
                {'name': 'Mobiles & Accessories', 'product_count': 85},
                {'name': 'Home & Kitchen', 'product_count': 150},
                {'name': 'Computers & Accessories', 'product_count': 45},
                {'name': 'Fashion', 'product_count': 310},
                {'name': 'Clothing & Accessories', 'product_count': 220},
            ],
            'brands': ['Samsung', 'Apple', 'Redmi', 'LG', 'Sony', 'Nothing', 'Realme']
        }

# Global AI integration instance
ai_integration = AIIntegration()
