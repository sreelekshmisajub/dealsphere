"""
Django admin configuration for core models
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, Merchant, Category, Brand, Product, Offer, Cart, CartItem,
    PriceMatchRequest, Notification, Order, OrderItem, UserActivity, PriceHistory
)

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_merchant', 'is_verified', 'created_at']
    list_filter = ['is_merchant', 'is_verified', 'is_staff', 'is_superuser', 'created_at']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    ordering = ['-created_at']
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('DealSphere Info', {'fields': ('phone', 'is_merchant', 'is_verified', 'location_lat', 'location_lng')}),
    )

@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ['shop_name', 'user', 'verified', 'rating', 'total_reviews', 'delivery_radius_km', 'created_at']
    list_filter = ['verified', 'created_at']
    search_fields = ['shop_name', 'user__username', 'user__email']
    readonly_fields = ['total_reviews']
    ordering = ['-created_at']

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'level', 'created_at']
    list_filter = ['level', 'created_at']
    search_fields = ['name']
    ordering = ['level', 'name']

@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']
    ordering = ['name']

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'brand', 'barcode', 'amazon_price', 'flipkart_price', 'created_at']
    list_filter = ['category', 'brand', 'created_at']
    search_fields = ['name', 'barcode']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ['product', 'merchant', 'price', 'discount_percentage', 'delivery_time_hours', 'is_active', 'created_at']
    list_filter = ['is_active', 'merchant', 'created_at']
    search_fields = ['product__name', 'merchant__shop_name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['user', 'created_at', 'updated_at']
    search_fields = ['user__username', 'user__email']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['cart', 'product', 'quantity', 'added_at']
    list_filter = ['added_at']
    search_fields = ['cart__user__username', 'product__name']
    readonly_fields = ['added_at']
    ordering = ['-added_at']

@admin.register(PriceMatchRequest)
class PriceMatchRequestAdmin(admin.ModelAdmin):
    list_display = ['user', 'merchant', 'product', 'requested_price', 'status', 'created_at']
    list_filter = ['status', 'merchant', 'created_at']
    search_fields = ['user__username', 'merchant__shop_name', 'product__name']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'notification_type', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['user__username', 'title']
    readonly_fields = ['created_at']
    ordering = ['-created_at']

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'total_amount', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['user__username', 'id']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['-created_at']

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['order', 'product', 'merchant', 'quantity', 'price', 'delivery_time_hours']
    list_filter = ['merchant', 'created_at']
    search_fields = ['order__id', 'product__name', 'merchant__shop_name']
    readonly_fields = ['created_at']
    ordering = ['-created_at']

@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ['user', 'activity_type', 'product', 'merchant', 'created_at']
    list_filter = ['activity_type', 'created_at']
    search_fields = ['user__username', 'product__name', 'merchant__shop_name']
    readonly_fields = ['created_at']
    ordering = ['-created_at']

@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ['product', 'source', 'price', 'merchant', 'created_at']
    list_filter = ['source', 'created_at']
    search_fields = ['product__name', 'merchant__shop_name']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
