"""
URL configuration for AI Engine app
"""

from django.urls import path
from . import views

app_name = 'ai_engine'

urlpatterns = [
    # ML Ranking endpoints
    path('rank/', views.MLRankingView.as_view(), name='ml_ranking'),
    path('rank/update_weights/', views.update_ranking_weights, name='update_ranking_weights'),
    
    # Computer Vision endpoints
    path('identify/', views.ProductIdentificationView.as_view(), name='product_identification'),
    
    # Barcode Scanner endpoints
    path('barcode/scan/', views.BarcodeScanningView.as_view(), name='barcode_scan'),
    path('barcode/search/', views.search_by_product_name, name='search_by_name'),
    path('barcode/stats/', views.get_database_statistics, name='barcode_stats'),
    
    # Basket Optimization endpoints
    path('basket/optimize/', views.BasketOptimizationView.as_view(), name='basket_optimize'),
    
    # Price Prediction endpoints
    path('price/predict/', views.PricePredictionView.as_view(), name='price_predict'),
    path('price/insights/', views.MarketInsightsView.as_view(), name='market_insights'),
    
    # Model Management endpoints
    path('models/train/', views.ModelTrainingView.as_view(), name='model_training'),
    path('models/status/', views.ModelStatusView.as_view(), name='model_status'),
    
    # Health check
    path('health/', views.health_check, name='health_check'),
]
