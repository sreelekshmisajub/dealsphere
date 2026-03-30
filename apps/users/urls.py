"""
URL configuration for Users app
"""

from django.urls import path
from . import views

app_name = 'users'

urlpatterns = [
    # Authentication
    path('register/', views.UserRegistrationView.as_view(), name='register'),
    path('login/', views.UserLoginView.as_view(), name='login'),
    path('profile/', views.UserProfileView.as_view(), name='profile'),
    
    # Product Search
    path('search/', views.ProductSearchView.as_view(), name='product_search'),
    path('recommendations/', views.get_recommended_products, name='recommendations'),
    
    # Cart Management
    path('cart/', views.CartView.as_view(), name='cart'),
    path('cart/add/', views.AddToCartView.as_view(), name='add_to_cart'),
    path('cart/update/<int:product_id>/', views.UpdateCartItemView.as_view(), name='update_cart_item'),
    path('cart/remove/<int:product_id>/', views.RemoveFromCartView.as_view(), name='remove_from_cart'),
    path('checkout/', views.CheckoutView.as_view(), name='checkout'),
    path('orders/', views.OrderHistoryView.as_view(), name='orders'),
    
    # User Activities
    path('activity/', views.UserActivityView.as_view(), name='user_activity'),
    path('location/', views.update_user_location, name='update_location'),
]
