# DealSphere AI Integration - Complete System Flow

##  Overview

This document outlines the complete integration of AI modules with the Django backend, ensuring all ML features work seamlessly with real datasets.

##  System Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend    │    │  Django API    │    │   AI Engine    │
│   (Templates)  │◄──►│   (Views)      │◄──►│  (ML Models)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                        │                        │
         ▼                        ▼                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   User Data    │    │  Real Datasets  │    │  Cache Layer    │
│  (Activities)  │    │ (CSV Files)    │    │   (Redis)       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🔗 Integration Points

### 1. ML Ranking Integration

**Flow:**
```
User Search → API View → AI Service → ML Ranker → Ranked Results → Frontend
```

**Files:**
- `apps/api/views_ai.py` - `ranked_products()`
- `apps/api/services_ai.py` - `search_products_with_ai()`
- `apps/ai_engine/integrations.py` - `rank_products()`

**Real Dataset Connection:**
```python
# Loads real data from CSV files
amazon_data = pd.read_csv('dataset/amazon.csv')
flipkart_data = pd.read_csv('dataset/marketing_sample_for_flipkart_com-ecommerce__20191101_20191130__15k_data.csv')
local_data = pd.read_csv('dataset/local_store_offer_dataset.csv')

# Trains ML model with real data
self.ml_ranker.load_data(amazon_data, flipkart_data, local_data)
self.ml_ranker.train_model()
```

### 2. Basket Optimization Integration
python manage.py migrate
**Flow:**
```
User Cart → API View → AI Service → Basket Optimizer → Optimization Results → Frontend
```

**Files:**
- `apps/api/views_ai.py` - `basket_optimization()`
- `apps/api/services_ai.py` - `optimize_user_basket()`
- `apps/ai_engine/integrations.py` - `optimize_basket()`

**Real Dataset Connection:**
```python
# Uses real offers from database
cart_items = CartItem.objects.filter(cart__user=user).select_related('product')
offers_data = []
for item in cart_items:
    product_offers = Offer.objects.filter(product=item.product).select_related('merchant')
    # Real merchant data used for optimization
```

### 3. Price Prediction Integration

**Flow:**
```
Product View → API View → AI Service → Price Predictor → Predictions → Notifications
```

**Files:**
- `apps/api/views_ai.py` - `price_prediction()`
- `apps/api/services_ai.py` - `predict_prices()`
- `apps/ai_engine/integrations.py` - `predict_price_trends()`

**Real Dataset Connection:**
```python
# Uses real price history
price_history = PriceHistory.objects.filter(product=product).order_by('created_at')
prices = [float(ph.price) for ph in price_history]

# LSTM model trained on real price data
self.price_predictor.load_price_data(amazon_data, flipkart_data, local_data)
self.price_predictor.train_model()
```

### 4. Smart Notifications Integration

**Flow:**
```
AI Engine → Smart Notifications → API View → User Notification → Frontend
```

**Files:**
- `apps/api/views_ai.py` - `smart_notifications()`
- `apps/api/services_ai.py` - `get_smart_notifications()`
- `apps/ai_engine/integrations.py` - `generate_smart_notifications()`

**Real Dataset Connection:**
```python
# Based on real user activity and predictions
watched_products = self._get_watched_products(user)
predictions = self.predict_price_trends(product_ids, days_ahead)
# Real price drop alerts generated
```

## 🛠️ URL Integration

### Main URLs (`dealsphere/urls.py`)
```python
urlpatterns = [
    # ... existing URLs ...
    path('api/v1/ai/', include('apps.api.urls_ai')),
]
```

### AI URLs (`apps/api/urls_ai.py`)
```python
urlpatterns = [
    path('ranked-products/', views_ai.ranked_products, name='ranked_products'),
    path('basket-optimize/', views_ai.basket_optimization, name='basket_optimization'),
    path('price-predict/', views_ai.price_prediction, name='price_prediction'),
    path('barcode-search/', views_ai.barcode_search, name='barcode_search'),
    path('identify-product/', views_ai.product_identification, name='product_identification'),
    path('smart-notifications/', views_ai.smart_notifications, name='smart_notifications'),
    path('recommendations/', views_ai.personalized_recommendations, name='personalized_recommendations'),
    path('ai-insights/', views_ai.ai_insights, name='ai_insights'),
]
```

## 🔄 Data Flow Examples

### 1. Product Search with AI Ranking

```python
# User searches for "laptop"
GET /api/v1/ai/ranked-products/?product_ids=1,2,3&user_id=123

# Flow:
# 1. API receives request
# 2. AI Service gets user preferences
# 3. ML Ranker scores products based on:
#    - User's past searches
#    - Price competitiveness
#    - Merchant ratings
#    - Location proximity
#    - Search relevance
# 4. Returns ranked products with ML scores
```

### 2. Basket Optimization

```python
# User optimizes cart
POST /api/v1/ai/basket-optimize/

# Flow:
# 1. Get user's cart items from database
# 2. Find all available offers for each product
# 3. Calculate optimal purchase strategy:
#    - Single store vs split purchase
#    - Delivery costs
#    - Time costs
# 4. Return optimization with real savings
```

### 3. Price Prediction

```python
# User wants price prediction
GET /api/v1/ai/price-predict/?product_ids=1,2,3&days_ahead=7

# Flow:
# 1. Get historical price data from PriceHistory
# 2. Use LSTM model to predict future prices
# 3. Calculate confidence scores
# 4. Return predictions with trend analysis
```

## 📱 Frontend Integration

### JavaScript Integration Points

```javascript
// 1. ML Ranking
fetch('/api/v1/ai/ranked-products/', {
    method: 'GET',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken')
    }
})
.then(response => response.json())
.then(data => {
    // Display ranked products with ML scores
    displayRankedProducts(data.products);
});

// 2. Basket Optimization
fetch('/api/v1/ai/basket-optimize/', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken')
    }
})
.then(response => response.json())
.then(data => {
    // Show optimization results
    displayOptimization(data);
});

// 3. Price Predictions
fetch('/api/v1/ai/price-predict/', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken')
    },
    body: JSON.stringify({
        product_ids: [1, 2, 3],
        days_ahead: 7
    })
})
.then(response => response.json())
.then(data => {
    // Display price predictions
    displayPricePredictions(data.predictions);
});
```

## 🗄️ Real Dataset Usage

### Amazon Dataset (1,467 products)
```python
# Used for:
- Product names and categories
- Price comparisons
- Rating data
- ML ranking features

amazon_data = pd.read_csv('dataset/amazon.csv')
products = amazon_data[['product_id', 'product_name', 'category', 'discounted_price', 'actual_price', 'rating']]
```

### Flipkart Dataset (15,000+ products)
```python
# Used for:
- Additional product data
- Price validation
- Market coverage
- Competitor analysis

flipkart_data = pd.read_csv('dataset/marketing_sample_for_flipkart_com-ecommerce__20191101_20191130__15k_data.csv')
```

### Local Store Dataset (6,000+ offers)
```python
# Used for:
- Local merchant data
- Delivery time calculations
- Geographic optimization
- Real-time inventory

local_data = pd.read_csv('dataset/local_store_offer_dataset.csv')
local_offers = local_data[['store_name', 'product_name', 'offer_price_inr', 'original_price_inr']]
```

## ⚡ Performance Optimization

### Caching Strategy
```python
# AI results cached for performance
cache_key = f"ranked_products_{user.id}_{hash(search_query)}"
cache.set(cache_key, ranked_products, timeout=300)  # 5 minutes

# Basket optimization cached
cache_key = f"basket_optimization_{user.id}"
cache.set(cache_key, optimization_result, timeout=600)  # 10 minutes
```

### Asynchronous Processing
```python
# Heavy AI tasks processed asynchronously
from apps.ai_engine.tasks import optimize_user_basket_async

# Trigger async basket optimization
optimize_user_basket_async.delay(user.id)

# Async image processing
process_product_image.delay(user.id, image_data, image_name)
```

## 🔧 Configuration

### AI Settings (`dealsphere/settings_ai.py`)
```python
AI_SETTINGS = {
    'DATASET_PATHS': {
        'amazon': 'dataset/amazon.csv',
        'flipkart': 'dataset/marketing_sample_for_flipkart_com-ecommerce__20191101_20191130__15k_data.csv',
        'local_stores': 'dataset/local_store_offer_dataset.csv'
    },
    'CACHE_TIMEOUTS': {
        'product_ranking': 300,  # 5 minutes
        'basket_optimization': 600,  # 10 minutes
        'price_prediction': 1800,  # 30 minutes
    }
}
```

### Celery Tasks
```python
# Periodic AI tasks
periodic_tasks = {
    'train_models': {
        'task': 'apps.ai_engine.tasks.train_ai_models',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
    'generate_notifications': {
        'task': 'apps.ai_engine.tasks.generate_smart_notifications',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
    }
}
```

## 📊 Monitoring & Logging

### AI Performance Metrics
```python
# Track model performance
logger.info(f"ML ranking completed for {len(products)} products")
logger.info(f"Basket optimization saved ₹{savings:.2f} for user {user.id}")

# Error handling
try:
    result = ai_integration.rank_products(user, products)
except Exception as e:
    logger.error(f"Error in ML ranking: {str(e)}")
    return fallback_results
```

### Cache Hit Rates
```python
# Monitor cache effectiveness
cache_hits = cache.get_many(cache_keys)
cache_misses = len(cache_keys) - len(cache_hits)
hit_rate = cache_hits / len(cache_keys) * 100
```

## 🔄 End-to-End Testing

### Test Scenarios

1. **User Search Flow**
   - User searches "laptop"
   - AI ranks products based on preferences
   - Results show ML scores
   - User interaction tracked

2. **Basket Optimization Flow**
   - User adds items to cart
   - AI optimizes across stores
   - Shows real savings calculations
   - Recommendations provided

3. **Price Prediction Flow**
   - User views product
   - AI predicts 7-day trend
   - Confidence scores displayed
   - Alerts created for drops

4. **Smart Notifications Flow**
   - AI analyzes user activity
   - Generates personalized alerts
   - Price drop notifications sent
   - Recommendations updated

## 🚀 Deployment Checklist

### ✅ Integration Complete

- [x] ML ranking connected to product search
- [x] Basket optimizer integrated with cart
- [x] Price prediction using real data
- [x] Smart notification system active
- [x] All AI models use real datasets
- [x] No dummy values in system
- [x] Full pipeline tested end-to-end
- [x] Caching implemented for performance
- [x] Async processing for heavy tasks
- [x] Error handling and logging
- [x] Rate limiting for AI endpoints

### 🎯 System Ready

The DealSphere AI integration is now complete and ready for production. All ML features are connected to the Django backend using real datasets, providing intelligent shopping recommendations, price predictions, and personalized notifications to users.
