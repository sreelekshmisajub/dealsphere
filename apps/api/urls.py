"""
URL configuration for API app
"""

from django.urls import path
from . import views

app_name = 'api'

urlpatterns = [
    # Product Search and Discovery
    path('products/search/', views.ProductSearchView.as_view(), name='product_search'),
    path('products/ranked/', views.GetRankedResultsView.as_view(), name='get_ranked_results'),
    path('products/trending/', views.TrendingProductsView.as_view(), name='trending_products'),
    path('products/<int:product_id>/similar/', views.SimilarProductsView.as_view(), name='similar_products'),
    path('products/<int:product_id>/details/', views.get_product_details, name='product_details'),
    path('products/<int:product_id>/comparison/', views.get_price_comparison, name='price_comparison'),
    path('products/<int:product_id>/amazon-reviews/', views.AmazonProductReviewsView.as_view(), name='amazon_product_reviews'),
    path('products/<int:product_id>/amazon-snapshot/', views.AmazonProductSnapshotView.as_view(), name='amazon_product_snapshot'),
    path('products/<int:product_id>/offers/', views.ProductOffersView.as_view(), name='product_offers'),
    path('products/<int:product_id>/ranking/', views.ProductRankingView.as_view(), name='product_ranking'),
    path('external/female-footwear/', views.ExternalFemaleFootwearFeedView.as_view(), name='external_female_footwear'),
    path('external/product-search/', views.ExternalProductSearchView.as_view(), name='external_product_search'),
    path('external/product-details/', views.ExternalProductDetailsView.as_view(), name='external_product_details'),
    path('external/product-offers/', views.ExternalProductOffersView.as_view(), name='external_product_offers'),
    path('external/product-price-history/', views.ExternalProductPriceHistoryView.as_view(), name='external_product_price_history'),
    path('external/deals/', views.ExternalDealsView.as_view(), name='external_deals'),

    # AI/ML Features
    path('ai/identify/', views.ProductIdentificationView.as_view(), name='product_identification'),
    path('ai/barcode/', views.BarcodeSearchView.as_view(), name='barcode_search'),
    path('ai/basket-optimize/', views.BasketOptimizationView.as_view(), name='basket_optimization'),
    path('ai/smart-basket/', views.SmartCartBasketView.as_view(), name='smart_basket'),
    path('ai/price-predict/', views.PricePredictionView.as_view(), name='price_prediction'),
    path('ai/market-insights/', views.MarketInsightsView.as_view(), name='market_insights'),

    # Notifications
    path('notifications/', views.NotificationView.as_view(), name='notifications'),
    path('notifications/mark-read/', views.MarkNotificationReadView.as_view(), name='mark_notification_read'),
    path('notifications/unread-count/', views.NotificationUnreadCountView.as_view(), name='notification_unread_count'),

    # Deal Locks
    path('deals/lock/', views.DealLockCreateView.as_view(), name='deal_lock_create'),
    path('deals/locks/', views.DealLockListView.as_view(), name='deal_lock_list'),
    path('deals/locks/<int:pk>/', views.DealLockCancelView.as_view(), name='deal_lock_cancel'),

    # Price Match
    path('price-match/', views.PriceMatchRequestCreateView.as_view(), name='price_match_create'),
    path('price-match/list/', views.PriceMatchRequestListView.as_view(), name='price_match_list'),
    path('price-match/<int:pk>/', views.PriceMatchRequestDetailView.as_view(), name='price_match_detail'),

    # Price Alerts
    path('alerts/price/', views.PriceAlertCreateView.as_view(), name='price_alert_create'),
    path('alerts/price/list/', views.PriceAlertListView.as_view(), name='price_alert_list'),
    path('alerts/price/<int:pk>/', views.PriceAlertDeleteView.as_view(), name='price_alert_delete'),
]
