"""
Admin panel views for DealSphere
"""

from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework import serializers
from drf_spectacular.utils import extend_schema, inline_serializer
from django.db.models import Count, Avg, Sum, Q
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
import logging

from apps.core.access import IsAdminUser
from apps.core.models import User, Merchant, Product, Offer, PriceMatchRequest, Order, UserActivity, Category, Brand
from .serializers import (
    AdminUserSerializer, AdminMerchantSerializer, AdminProductSerializer,
    AdminOfferSerializer, AdminOrderSerializer, AdminPriceMatchSerializer, AdminDashboardSerializer,
    CategorySerializer, BrandSerializer, AdminBulkUserActionSerializer,
    AdminBulkMerchantVerificationSerializer,
)
from .services import AdminService

logger = logging.getLogger(__name__)
User = get_user_model()

class AdminDashboardView(generics.RetrieveAPIView):
    """Admin dashboard overview"""
    permission_classes = [IsAdminUser]
    serializer_class = AdminDashboardSerializer

    def get_object(self):
        return AdminService.get_dashboard_data()

class UserManagementView(generics.ListAPIView):
    """User management for admin"""
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = User.objects.all().order_by('-date_joined')
        
        # Filters
        is_merchant = self.request.query_params.get('is_merchant')
        is_verified = self.request.query_params.get('is_verified')
        is_active = self.request.query_params.get('is_active')
        
        if is_merchant is not None:
            queryset = queryset.filter(is_merchant=is_merchant.lower() == 'true')
        
        if is_verified is not None:
            queryset = queryset.filter(is_verified=is_verified.lower() == 'true')
        
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        # Search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )
        
        return queryset

class UserDetailView(generics.RetrieveUpdateDestroyAPIView):
    """User detail view for admin"""
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminUser]
    queryset = User.objects.all()

    def update(self, request, *args, **kwargs):
        try:
            partial = kwargs.pop('partial', False)
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)
            
            user = serializer.save()
            
            # Log admin action
            UserActivity.objects.create(
                user=request.user,
                activity_type='admin_user_updated',
                metadata={
                    'target_user_id': user.id,
                    'admin_changes': request.data
                }
            )
            
            return Response(serializer.data)
            
        except (ValidationError, DRFValidationError) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Admin user update error: {e}")
            return Response({'error': 'Failed to update user'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MerchantManagementView(generics.ListAPIView):
    """Merchant management for admin"""
    serializer_class = AdminMerchantSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = Merchant.objects.select_related('user').order_by('-created_at')
        
        # Filters
        verified = self.request.query_params.get('verified')
        rating_min = self.request.query_params.get('rating_min')
        
        if verified is not None:
            queryset = queryset.filter(verified=verified.lower() == 'true')
        
        if rating_min:
            queryset = queryset.filter(rating__gte=float(rating_min))
        
        # Search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(shop_name__icontains=search) |
                Q(user__email__icontains=search) |
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search)
            )
        
        return queryset

class MerchantVerificationView(generics.UpdateAPIView):
    """Verify merchant"""
    serializer_class = AdminMerchantSerializer
    permission_classes = [IsAdminUser]
    queryset = Merchant.objects.all()

    def update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            verified = request.data.get('verified', False)
            
            instance.verified = verified
            instance.save()
            
            # Update user verification status
            instance.user.is_verified = verified
            instance.user.save()
            
            # Log admin action
            UserActivity.objects.create(
                user=request.user,
                activity_type='admin_merchant_verified',
                merchant=instance,
                metadata={'verified': verified}
            )
            
            return Response({
                'message': f'Merchant {"verified" if verified else "unverified"} successfully',
                'merchant': self.get_serializer(instance).data
            })
            
        except Exception as e:
            logger.error(f"Merchant verification error: {e}")
            return Response({'error': 'Failed to verify merchant'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ProductManagementView(generics.ListAPIView):
    """Product management for admin"""
    serializer_class = AdminProductSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = Product.objects.select_related('category', 'brand').order_by('-created_at')
        
        # Filters
        category = self.request.query_params.get('category')
        brand = self.request.query_params.get('brand')
        has_barcode = self.request.query_params.get('has_barcode')
        
        if category:
            queryset = queryset.filter(category__name__icontains=category)
        
        if brand:
            queryset = queryset.filter(brand__name__icontains=brand)
        
        if has_barcode is not None:
            if has_barcode.lower() == 'true':
                queryset = queryset.filter(barcode__isnull=False).exclude(barcode='')
            else:
                queryset = queryset.filter(Q(barcode__isnull=True) | Q(barcode=''))
        
        # Search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(barcode__icontains=search) |
                Q(category__name__icontains=search) |
                Q(brand__name__icontains=search)
            )
        
        return queryset

class OfferManagementView(generics.ListAPIView):
    """Offer management for admin"""
    serializer_class = AdminOfferSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = Offer.objects.select_related('product', 'merchant', 'merchant__user').order_by('-created_at')
        
        # Filters
        is_active = self.request.query_params.get('is_active')
        merchant = self.request.query_params.get('merchant')
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        if merchant:
            queryset = queryset.filter(merchant__shop_name__icontains=merchant)
        
        if min_price:
            queryset = queryset.filter(price__gte=float(min_price))
        
        if max_price:
            queryset = queryset.filter(price__lte=float(max_price))
        
        # Search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(product__name__icontains=search) |
                Q(merchant__shop_name__icontains=search) |
                Q(product__barcode__icontains=search)
            )
        
        return queryset


class OrderManagementView(generics.ListAPIView):
    """Order management for admin"""
    serializer_class = AdminOrderSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = Order.objects.select_related('user').prefetch_related('items', 'items__product', 'items__merchant').order_by('-created_at')

        status_value = self.request.query_params.get('status')
        payment_status = self.request.query_params.get('payment_status')
        payment_method = self.request.query_params.get('payment_method')
        search = self.request.query_params.get('search')

        if status_value:
            queryset = queryset.filter(status=status_value)
        if payment_status:
            queryset = queryset.filter(payment_status=payment_status)
        if payment_method:
            queryset = queryset.filter(payment_method=payment_method)
        if search:
            queryset = queryset.filter(
                Q(user__email__icontains=search) |
                Q(items__product__name__icontains=search) |
                Q(items__source_name__icontains=search)
            ).distinct()

        return queryset

class PriceMatchManagementView(generics.ListAPIView):
    """Price match management for admin"""
    serializer_class = AdminPriceMatchSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = PriceMatchRequest.objects.select_related(
            'user', 'merchant', 'product', 'merchant__user'
        ).order_by('-created_at')
        
        # Filters
        status = self.request.query_params.get('status')
        merchant = self.request.query_params.get('merchant')
        
        if status:
            queryset = queryset.filter(status=status)
        
        if merchant:
            queryset = queryset.filter(merchant__shop_name__icontains=merchant)
        
        # Search
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(user__email__icontains=search) |
                Q(merchant__shop_name__icontains=search) |
                Q(product__name__icontains=search)
            )
        
        return queryset

class CategoryManagementView(generics.ListCreateAPIView):
    """Category management for admin"""
    serializer_class = CategorySerializer
    permission_classes = [IsAdminUser]
    queryset = Category.objects.all().order_by('level', 'name')

class BrandManagementView(generics.ListCreateAPIView):
    """Brand management for admin"""
    serializer_class = BrandSerializer
    permission_classes = [IsAdminUser]
    queryset = Brand.objects.all().order_by('name')

@extend_schema(responses=inline_serializer(
    name='AdminAnalyticsResponse',
    fields={
        'user_growth': serializers.ListField(),
        'merchant_performance': serializers.ListField(),
        'category_distribution': serializers.ListField(),
        'price_match_trends': serializers.ListField(),
        'geographic_distribution': serializers.DictField(),
    },
))
@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_analytics(request):
    """Get comprehensive admin analytics"""
    try:
        analytics = AdminService.get_analytics()
        return Response(analytics)
        
    except Exception as e:
        logger.error(f"Admin analytics error: {e}")
        return Response({'error': 'Failed to get analytics'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@extend_schema(responses=inline_serializer(
    name='AdminSystemHealthResponse',
    fields={
        'overall_status': serializers.CharField(),
        'database': serializers.CharField(required=False),
        'recent_activity_count': serializers.IntegerField(required=False),
        'error_rate': serializers.FloatField(required=False, allow_null=True),
        'avg_response_time_ms': serializers.FloatField(required=False, allow_null=True),
        'storage_usage': serializers.DictField(required=False),
        'last_check': serializers.CharField(),
        'error': serializers.CharField(required=False),
    },
))
@api_view(['GET'])
@permission_classes([IsAdminUser])
def system_health(request):
    """Get system health status"""
    try:
        health_data = AdminService.get_system_health()
        return Response(health_data)
        
    except Exception as e:
        logger.error(f"System health error: {e}")
        return Response({'error': 'Failed to get system health'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@extend_schema(
    request=AdminBulkUserActionSerializer,
    responses=inline_serializer(
        name='AdminBulkUserActionResponse',
        fields={
            'message': serializers.CharField(),
            'updated_count': serializers.IntegerField(),
        },
    ),
)
@api_view(['POST'])
@permission_classes([IsAdminUser])
def bulk_user_action(request):
    """Bulk action on users"""
    try:
        action = request.data.get('action')
        user_ids = request.data.get('user_ids', [])
        
        if not user_ids:
            return Response({'error': 'No user IDs provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        users = User.objects.filter(id__in=user_ids)
        updated_count = 0
        
        if action == 'activate':
            updated_count = users.update(is_active=True)
        elif action == 'deactivate':
            updated_count = users.update(is_active=False)
        elif action == 'verify':
            updated_count = users.update(is_verified=True)
        elif action == 'unverify':
            updated_count = users.update(is_verified=False)
        else:
            return Response({'error': 'Invalid action'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Log admin action
        UserActivity.objects.create(
            user=request.user,
            activity_type='admin_bulk_user_action',
            metadata={
                'action': action,
                'user_ids': user_ids,
                'updated_count': updated_count
            }
        )
        
        return Response({
            'message': f'Bulk {action} completed',
            'updated_count': updated_count
        })
        
    except Exception as e:
        logger.error(f"Bulk user action error: {e}")
        return Response({'error': 'Failed to perform bulk action'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@extend_schema(
    request=AdminBulkMerchantVerificationSerializer,
    responses=inline_serializer(
        name='AdminBulkMerchantVerificationResponse',
        fields={
            'message': serializers.CharField(),
            'updated_count': serializers.IntegerField(),
        },
    ),
)
@api_view(['POST'])
@permission_classes([IsAdminUser])
def bulk_merchant_verification(request):
    """Bulk verify/unverify merchants"""
    try:
        verified = request.data.get('verified', False)
        merchant_ids = request.data.get('merchant_ids', [])
        
        if not merchant_ids:
            return Response({'error': 'No merchant IDs provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        merchants = Merchant.objects.filter(id__in=merchant_ids)
        
        # Update merchant verification
        merchants.update(verified=verified)
        
        # Update user verification status
        User.objects.filter(merchant_profile__id__in=merchant_ids).update(is_verified=verified)
        
        # Log admin action
        UserActivity.objects.create(
            user=request.user,
            activity_type='admin_bulk_merchant_verification',
            metadata={
                'verified': verified,
                'merchant_ids': merchant_ids
            }
        )
        
        return Response({
            'message': f'Bulk {"verification" if verified else "unverification"} completed',
            'updated_count': len(merchant_ids)
        })
        
    except Exception as e:
        logger.error(f"Bulk merchant verification error: {e}")
        return Response({'error': 'Failed to perform bulk verification'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
