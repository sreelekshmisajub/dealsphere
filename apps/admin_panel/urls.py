"""
URL configuration for Admin Panel app
"""

from django.urls import path
from . import views

app_name = 'admin_panel'

urlpatterns = [
    # Dashboard
    path('dashboard/', views.AdminDashboardView.as_view(), name='dashboard'),
    path('analytics/', views.admin_analytics, name='analytics'),
    path('health/', views.system_health, name='system_health'),
    
    # User Management
    path('users/', views.UserManagementView.as_view(), name='user_management'),
    path('users/<int:pk>/', views.UserDetailView.as_view(), name='user_detail'),
    path('users/bulk-action/', views.bulk_user_action, name='bulk_user_action'),
    
    # Merchant Management
    path('merchants/', views.MerchantManagementView.as_view(), name='merchant_management'),
    path('merchants/<int:pk>/', views.MerchantVerificationView.as_view(), name='merchant_verification'),
    path('merchants/bulk-verify/', views.bulk_merchant_verification, name='bulk_merchant_verification'),
    
    # Product Management
    path('products/', views.ProductManagementView.as_view(), name='product_management'),
    
    # Offer Management
    path('offers/', views.OfferManagementView.as_view(), name='offer_management'),
    path('orders/', views.OrderManagementView.as_view(), name='order_management'),

    # Price Match Management
    path('price-matches/', views.PriceMatchManagementView.as_view(), name='price_match_management'),
    
    # Category & Brand Management
    path('categories/', views.CategoryManagementView.as_view(), name='category_management'),
    path('brands/', views.BrandManagementView.as_view(), name='brand_management'),
]
