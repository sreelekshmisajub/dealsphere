"""
AI-powered API URLs
URLs for ML ranking, basket optimization, price prediction, and smart notifications
"""

from django.urls import path
from . import views_ai

app_name = 'api_ai'

urlpatterns = [
    # ML Ranking
    path('ranked-products/', views_ai.ranked_products, name='ranked_products'),
    
    # Basket Optimization
    path('basket-optimize/', views_ai.basket_optimization, name='basket_optimization'),
    
    # Price Prediction
    path('price-predict/', views_ai.price_prediction, name='price_prediction'),
    
    # Barcode Search
    path('barcode-search/', views_ai.barcode_search, name='barcode_search'),
    
    # Product Identification
    path('identify-product/', views_ai.product_identification, name='product_identification'),
    
    # Smart Notifications
    path('smart-notifications/', views_ai.smart_notifications, name='smart_notifications'),
    
    # Personalized Recommendations
    path('recommendations/', views_ai.personalized_recommendations, name='personalized_recommendations'),
    
    # AI Insights
    path('ai-insights/', views_ai.ai_insights, name='ai_insights'),
]
