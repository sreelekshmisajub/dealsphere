"""
URL configuration for Merchants app
"""

from django.urls import path
from . import views

app_name = 'merchants'

urlpatterns = [
    path('register/', views.MerchantRegistrationView.as_view(), name='register'),
    path('dashboard/', views.MerchantDashboardView.as_view(), name='merchant_dashboard'),
    # Merchant Profile
    path('profile/', views.MerchantProfileView.as_view(), name='profile'),
    
    # Product Management
    path('products/add/', views.AddProductView.as_view(), name='add_product'),
    path('products/update/<int:product_id>/', views.UpdateProductView.as_view(), name='update_product'),
    path('products/', views.MerchantProductsView.as_view(), name='merchant_products'),
    
    # Offer Management
    path('offers/create/', views.CreateOfferView.as_view(), name='create_offer'),
    path('offers/update/<int:offer_id>/', views.UpdateOfferView.as_view(), name='update_offer'),
    path('offers/', views.MerchantOffersView.as_view(), name='merchant_offers'),
    path('orders/', views.MerchantOrdersView.as_view(), name='merchant_orders'),
    path('price/bulk-update/', views.update_price_bulk, name='bulk_update_price'),
    
    # Price Match Handling
    path('price-match/requests/', views.PriceMatchRequestsView.as_view(), name='price_match_requests'),
    path('price-match/handle/<int:request_id>/', views.HandlePriceMatchView.as_view(), name='handle_price_match'),
    
    # Analytics
    path('analytics/', views.merchant_analytics, name='merchant_analytics'),
]
