"""
Main URL configuration for DealSphere
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

from .site_views import (
    AdminDashboardPageView,
    AdminAnalyticsPageView,
    AdminDataPageView,
    AdminDealsPageView,
    AdminLoginPageView,
    AdminLogsPageView,
    AdminMerchantsPageView,
    AdminMLPageView,
    AdminNotificationsPageView,
    AdminProductsPageView,
    AdminProfilePageView,
    AdminUsersPageView,
    BarcodeScannerPageView,
    BasketPageView,
    CartPageView,
    CheckoutPageView,
    DashboardProductDetailPageView,
    DashboardSearchResultsPageView,
    DashboardCartAddView,
    DashboardCartRemoveView,
    DashboardCartUpdateView,
    DealLockPageView,
    FeatureStatusPageView,
    HomePageView,
    LoginPageView,
    MerchantDashboardPageView,
    MerchantInventoryPageView,
    MerchantAddProductPageView,
    MerchantPriceMatchRequestsPageView,
    MerchantDealsPageView,
    MerchantDeliverySettingsPageView,
    MerchantAnalyticsPageView,
    MerchantNotificationsPageView,
    MerchantProfilePageView,
    NotificationsPageView,
    OrderHistoryPageView,
    ProductDetailPageView,
    ProfilePageView,
    RegisterPageView,
    SearchResultsPageView,
    UserDashboardPageView,
    VisualSearchPageView,
    admin_dashboard_legacy_redirect,
    merchant_dashboard_legacy_redirect,
    logout_redirect,
    register_merchant_redirect,
)

urlpatterns = [
    # Frontend pages
    path('', HomePageView.as_view(), name='index'),
    path('about/', HomePageView.as_view(template_name='about.html'), name='about'),
    path('deals/', SearchResultsPageView.as_view(), name='deals'),
    path(
        'price-alert/',
        FeatureStatusPageView.as_view(
            extra_context={
                'feature_title': 'Price Alert Module',
                'feature_copy': 'The notification model is live, but target-price alert scheduling is not fully wired into the frontend yet.',
                'feature_cta_label': 'Open Notifications',
                'feature_cta_url': '/notifications/',
            }
        ),
        name='price_alert',
    ),
    path(
        'price-history/',
        FeatureStatusPageView.as_view(
            extra_context={
                'feature_title': 'Price History Tracker',
                'feature_copy': 'Real price history is stored per product. The dedicated chart view still needs a frontend chart wired to those records.',
                'feature_cta_label': 'Search Products',
                'feature_cta_url': '/products/search/',
            }
        ),
        name='price_history_tracker',
    ),
    path(
        'spending-analysis/',
        FeatureStatusPageView.as_view(
            extra_context={
                'feature_title': 'Spend Lens',
                'feature_copy': 'Basket and spending analysis is available through the real cart and recommendation flows. A dedicated analytics page is still pending.',
                'feature_cta_label': 'Open Dashboard',
                'feature_cta_url': '/dashboard/',
            }
        ),
        name='spending_analysis',
    ),
    path(
        'gift-cards/',
        FeatureStatusPageView.as_view(
            extra_context={
                'feature_title': 'Gift Card Feed',
                'feature_copy': 'No live gift-card partner feed is integrated in this workspace, so this module stays disabled to avoid fake frontend data.',
                'feature_cta_label': 'Back to Home',
                'feature_cta_url': '/',
            }
        ),
        name='gift_cards',
    ),
    path('login/', LoginPageView.as_view(), name='login'),
    path('admin-login/', AdminLoginPageView.as_view(), name='admin_login'),
    path('register/', RegisterPageView.as_view(), name='register'),
    path('register/merchant/', register_merchant_redirect, name='register_merchant'),
    path('logout/', logout_redirect, name='logout'),
    path('products/search/', SearchResultsPageView.as_view(), name='product_search'),
    path('products/<int:product_id>/', ProductDetailPageView.as_view(), name='product_detail'),
    path('cart/', CartPageView.as_view(), name='cart'),
    path('dashboard/', UserDashboardPageView.as_view(), name='user_dashboard'),
    path('dashboard/results/', DashboardSearchResultsPageView.as_view(), name='dashboard_results'),
    path('dashboard/product/<int:product_id>/', DashboardProductDetailPageView.as_view(), name='dashboard_product_detail'),
    path('dashboard/barcode/', BarcodeScannerPageView.as_view(), name='dashboard_barcode'),
    path('dashboard/visual-search/', VisualSearchPageView.as_view(), name='dashboard_visual_search'),
    path('dashboard/basket/', BasketPageView.as_view(), name='dashboard_basket'),
    path('dashboard/cart/add/', DashboardCartAddView.as_view(), name='dashboard_cart_add'),
    path('dashboard/cart/update/<int:product_id>/', DashboardCartUpdateView.as_view(), name='dashboard_cart_update'),
    path('dashboard/cart/remove/<int:product_id>/', DashboardCartRemoveView.as_view(), name='dashboard_cart_remove'),
    path('dashboard/checkout/', CheckoutPageView.as_view(), name='dashboard_checkout'),
    path('dashboard/orders/', OrderHistoryPageView.as_view(), name='dashboard_orders'),
    path('dashboard/deal-lock/', DealLockPageView.as_view(), name='dashboard_deal_lock'),
    path('dashboard/deal-lock/<int:product_id>/', DealLockPageView.as_view(), name='dashboard_deal_lock_product'),
    path('dashboard/notifications/', NotificationsPageView.as_view(), name='dashboard_notifications'),
    path('dashboard/profile/', ProfilePageView.as_view(), name='dashboard_profile'),
    path('activity/', UserDashboardPageView.as_view(), name='user_activity'),
    path('notifications/', NotificationsPageView.as_view(), name='notifications'),
    path('profile/', ProfilePageView.as_view(), name='profile'),
    path('dashboard/merchant/', MerchantDashboardPageView.as_view(), name='merchant_dashboard'),
    path('dashboard/merchant/products/', MerchantInventoryPageView.as_view(), name='merchant_inventory'),
    path('dashboard/merchant/products/add/', MerchantAddProductPageView.as_view(), name='merchant_add_product'),
    path('dashboard/merchant/requests/', MerchantPriceMatchRequestsPageView.as_view(), name='merchant_requests'),
    path('dashboard/merchant/deals/', MerchantDealsPageView.as_view(), name='merchant_deals'),
    path('dashboard/merchant/delivery/', MerchantDeliverySettingsPageView.as_view(), name='merchant_delivery'),
    path('dashboard/merchant/analytics/', MerchantAnalyticsPageView.as_view(), name='merchant_analytics_dashboard'),
    path('dashboard/merchant/notifications/', MerchantNotificationsPageView.as_view(), name='merchant_notifications'),
    path('dashboard/merchant/profile/', MerchantProfilePageView.as_view(), name='merchant_profile_dashboard'),
    path('merchant/dashboard/', merchant_dashboard_legacy_redirect, name='merchant_dashboard_legacy'),
    path('dashboard/admin/', AdminDashboardPageView.as_view(), name='admin_dashboard'),
    path('dashboard/admin/users/', AdminUsersPageView.as_view(), name='admin_users'),
    path('dashboard/admin/merchants/', AdminMerchantsPageView.as_view(), name='admin_merchants'),
    path('dashboard/admin/products/', AdminProductsPageView.as_view(), name='admin_products'),
    path('dashboard/admin/deals/', AdminDealsPageView.as_view(), name='admin_deals'),
    path('dashboard/admin/data/', AdminDataPageView.as_view(), name='admin_data'),
    path('dashboard/admin/ml/', AdminMLPageView.as_view(), name='admin_ml'),
    path('dashboard/admin/notifications/', AdminNotificationsPageView.as_view(), name='admin_notifications'),
    path('dashboard/admin/analytics/', AdminAnalyticsPageView.as_view(), name='admin_analytics'),
    path('dashboard/admin/logs/', AdminLogsPageView.as_view(), name='admin_logs'),
    path('dashboard/admin/profile/', AdminProfilePageView.as_view(), name='admin_profile'),
    path('admin/dashboard/', admin_dashboard_legacy_redirect, name='admin_dashboard_legacy'),

    # Admin
    path('admin/', admin.site.urls),
    
    # API Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    
    # API v1 Endpoints
    path('api/v1/auth/', include(('apps.users.urls', 'users'), namespace='auth_api')),
    path('api/v1/users/', include(('apps.users.urls', 'users'), namespace='users_api')),
    path('api/v1/merchants/', include(('apps.merchants.urls', 'merchants'), namespace='merchants_api')),
    path('api/v1/admin/', include(('apps.admin_panel.urls', 'admin_panel'), namespace='admin_api')),
    path('api/v1/', include(('apps.api.urls', 'api'), namespace='core_api')),
    path('api/v1/ai-engine/', include(('apps.ai_engine.urls', 'ai_engine'), namespace='ai_engine_api')),
    
    # Health Check
    path('health/', lambda request: JsonResponse({'status': 'ok', 'service': 'dealsphere'}), name='health'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
