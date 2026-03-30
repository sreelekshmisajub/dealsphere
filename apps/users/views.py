"""
User module views for DealSphere
"""

from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
import logging

from apps.core.access import IsCustomerUser
from apps.core.models import User, Product, Cart, CartItem, Order, UserActivity
from .serializers import (
    UserRegistrationSerializer, UserLoginSerializer,
    UserProfileSerializer, ProductSearchSerializer,
    CartSerializer, CartItemSerializer, OrderSerializer,
    LocationUpdateSerializer, AddToCartRequestSerializer,
    CartQuantitySerializer, CheckoutRequestSerializer,
    UserActivityResponseSerializer,
)
from .services import CartOrderService, UserService, SearchService
from utils.validators import validate_phone_number, validate_location

logger = logging.getLogger(__name__)

class UserRegistrationView(generics.CreateAPIView):
    """User registration endpoint"""
    permission_classes = [permissions.AllowAny]
    serializer_class = UserRegistrationSerializer

    def post(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            user = serializer.save()

            return Response(
                {
                    'message': 'Registration completed successfully. Please log in.',
                    'user': UserProfileSerializer(user).data,
                },
                status=status.HTTP_201_CREATED,
            )
                
        except (ValidationError, DRFValidationError) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"User registration error: {e}")
            return Response({'error': 'Registration failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class UserLoginView(generics.GenericAPIView):
    """User login endpoint"""
    permission_classes = [permissions.AllowAny]
    serializer_class = UserLoginSerializer

    def post(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            email = serializer.validated_data['email']
            password = serializer.validated_data['password']
            
            user = User.objects.filter(email__iexact=email).first()
            if user:
                user = authenticate(username=user.username, password=password)
            
            if not user or not user.is_active:
                return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
            
            # Log activity
            UserActivity.objects.create(
                user=user,
                activity_type='user_login',
                metadata={'login_method': 'api'}
            )
            
            # Generate JWT tokens
            refresh = RefreshToken.for_user(user)
            
            return Response({
                'user': UserProfileSerializer(user).data,
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            }, status=status.HTTP_200_OK)
            
        except DRFValidationError as e:
            return Response({'error': e.detail}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"User login error: {e}")
            return Response({'error': 'Login failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class UserProfileView(generics.RetrieveUpdateAPIView):
    """User profile view"""
    serializer_class = UserProfileSerializer
    permission_classes = [IsCustomerUser]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        try:
            # Validate location if provided
            if 'location_lat' in request.data or 'location_lng' in request.data:
                lat = request.data.get('location_lat')
                lng = request.data.get('location_lng')
                validate_location(lat, lng)
            
            # Validate phone if provided
            if 'phone' in request.data and request.data['phone']:
                validate_phone_number(request.data['phone'])
            
            return super().update(request, *args, **kwargs)
            
        except (ValidationError, DRFValidationError) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Profile update error: {e}")
            return Response({'error': 'Profile update failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ProductSearchView(generics.ListAPIView):
    """Product search endpoint for users"""
    serializer_class = ProductSearchSerializer
    permission_classes = [IsCustomerUser]

    def get_queryset(self):
        query = self.request.query_params.get('q', '').strip()
        category = self.request.query_params.get('category', '').strip()
        min_price = self.request.query_params.get('min_price')
        max_price = self.request.query_params.get('max_price')
        sort_by = self.request.query_params.get('sort_by', 'relevance')
        
        return SearchService.search_products(
            query=query,
            category=category,
            min_price=min_price,
            max_price=max_price,
            sort_by=sort_by,
            user=self.request.user
        )

class CartView(generics.RetrieveUpdateAPIView):
    """User cart view"""
    serializer_class = CartSerializer
    permission_classes = [IsCustomerUser]

    def get_object(self):
        cart, created = Cart.objects.get_or_create(user=self.request.user)
        return cart

class AddToCartView(generics.CreateAPIView):
    """Add item to cart"""
    serializer_class = CartItemSerializer
    permission_classes = [IsCustomerUser]

    @extend_schema(request=AddToCartRequestSerializer, responses=inline_serializer(
        name='AddToCartResponse',
        fields={
            'message': serializers.CharField(),
            'cart_item': CartItemSerializer(),
            'selected_source': serializers.DictField(),
        },
    ))
    def post(self, request, *args, **kwargs):
        try:
            product_id = request.data.get('product_id')
            quantity = int(request.data.get('quantity', 1))
            source = request.data.get('source')
            merchant_id = request.data.get('merchant_id')

            cart_item, candidate = CartOrderService.add_to_cart(
                request.user,
                product_id=product_id,
                quantity=quantity,
                source=source,
                merchant_id=merchant_id,
            )
            
            return Response({
                'message': 'Item added to cart',
                'cart_item': CartItemSerializer(cart_item).data,
                'selected_source': {
                    'source': candidate['source'],
                    'source_name': candidate['source_name'],
                    'unit_price': float(candidate['price']),
                }
            }, status=status.HTTP_201_CREATED)
            
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)
        except (ValidationError, DRFValidationError) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Add to cart error: {e}")
            return Response({'error': 'Failed to add to cart'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UpdateCartItemView(generics.UpdateAPIView):
    """Update cart item quantity"""
    serializer_class = CartItemSerializer
    permission_classes = [IsCustomerUser]

    @extend_schema(request=CartQuantitySerializer, responses=inline_serializer(
        name='UpdateCartItemResponse',
        fields={
            'message': serializers.CharField(),
            'cart_item': CartItemSerializer(required=False),
        },
    ))
    def patch(self, request, *args, **kwargs):
        try:
            product_id = kwargs.get('product_id')
            quantity = int(request.data.get('quantity', 1))
            item = CartOrderService.update_cart_item(request.user, product_id, quantity)

            if item is None:
                return Response({'message': 'Item removed from cart'}, status=status.HTTP_200_OK)

            return Response({
                'message': 'Cart item updated',
                'cart_item': CartItemSerializer(item).data
            })
        except Cart.DoesNotExist:
            return Response({'error': 'Cart not found'}, status=status.HTTP_404_NOT_FOUND)
        except CartItem.DoesNotExist:
            return Response({'error': 'Cart item not found'}, status=status.HTTP_404_NOT_FOUND)
        except (ValidationError, DRFValidationError, ValueError) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Update cart item error: {e}")
            return Response({'error': 'Failed to update cart item'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class RemoveFromCartView(generics.DestroyAPIView):
    """Remove item from cart"""
    serializer_class = CartItemSerializer
    permission_classes = [IsCustomerUser]

    @extend_schema(responses=inline_serializer(
        name='RemoveFromCartResponse',
        fields={'message': serializers.CharField()},
    ))
    def delete(self, request, *args, **kwargs):
        try:
            product_id = kwargs.get('product_id')
            
            cart = Cart.objects.get(user=request.user)
            cart_item = CartItem.objects.get(cart=cart, product_id=product_id)
            
            # Log activity
            UserActivity.objects.create(
                user=request.user,
                activity_type='remove_from_cart',
                product=cart_item.product
            )
            
            cart_item.delete()
            
            return Response({'message': 'Item removed from cart'}, status=status.HTTP_200_OK)
            
        except Cart.DoesNotExist:
            return Response({'error': 'Cart not found'}, status=status.HTTP_404_NOT_FOUND)
        except CartItem.DoesNotExist:
            return Response({'error': 'Item not in cart'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Remove from cart error: {e}")
            return Response({'error': 'Failed to remove from cart'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CheckoutView(generics.GenericAPIView):
    """Create order from current cart"""
    serializer_class = CheckoutRequestSerializer
    permission_classes = [IsCustomerUser]

    @extend_schema(request=CheckoutRequestSerializer, responses=inline_serializer(
        name='CheckoutResponse',
        fields={
            'message': serializers.CharField(),
            'order': OrderSerializer(),
            'external_checkout_links': serializers.ListField(),
        },
    ))
    def post(self, request, *args, **kwargs):
        try:
            delivery_address = request.data.get('delivery_address', '').strip()
            payment_method = request.data.get('payment_method', '').strip()
            order, external_links = CartOrderService.create_order_from_cart(
                request.user,
                delivery_address=delivery_address,
                payment_method=payment_method,
            )
            return Response(
                {
                    'message': 'Order created successfully',
                    'order': OrderSerializer(order).data,
                    'external_checkout_links': external_links,
                },
                status=status.HTTP_201_CREATED,
            )
        except (ValidationError, DRFValidationError) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Checkout error: {e}")
            return Response({'error': 'Failed to create order'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class OrderHistoryView(generics.ListAPIView):
    """List user orders"""
    serializer_class = OrderSerializer
    permission_classes = [IsCustomerUser]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related('items', 'items__product', 'items__merchant').order_by('-created_at')

class UserActivityView(generics.ListAPIView):
    """User activity history"""
    serializer_class = UserActivityResponseSerializer
    permission_classes = [IsCustomerUser]

    @extend_schema(responses=UserActivityResponseSerializer)
    def get(self, request, *args, **kwargs):
        try:
            limit = int(request.query_params.get('limit', 20))
            activities = UserActivity.objects.filter(
                user=request.user
            ).select_related('product', 'merchant').order_by('-created_at')[:limit]
            
            activity_data = []
            for activity in activities:
                data = {
                    'activity_type': activity.activity_type,
                    'created_at': activity.created_at,
                    'metadata': activity.metadata
                }
                
                if activity.product:
                    data['product'] = {
                        'id': activity.product.id,
                        'name': activity.product.name,
                        'image_url': activity.product.image_url
                    }
                
                if activity.merchant:
                    data['merchant'] = {
                        'id': activity.merchant.id,
                        'shop_name': activity.merchant.shop_name
                    }
                
                activity_data.append(data)
            
            return Response({'activities': activity_data})
            
        except Exception as e:
            logger.error(f"Get user activity error: {e}")
            return Response({'error': 'Failed to get activity history'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@extend_schema(request=LocationUpdateSerializer, responses=inline_serializer(
    name='LocationUpdateResponse',
    fields={'message': serializers.CharField()},
))
@api_view(['POST'])
@permission_classes([IsCustomerUser])
def update_user_location(request):
    """Update user location"""
    try:
        lat = request.data.get('lat')
        lng = request.data.get('lng')
        
        validate_location(lat, lng)
        
        user = request.user
        user.location_lat = lat
        user.location_lng = lng
        user.save()
        
        # Log activity
        UserActivity.objects.create(
            user=user,
            activity_type='location_update',
            metadata={'lat': lat, 'lng': lng}
        )
        
        return Response({'message': 'Location updated successfully'})
        
    except (ValidationError, DRFValidationError) as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        logger.error(f"Update location error: {e}")
        return Response({'error': 'Failed to update location'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@extend_schema(responses=inline_serializer(
    name='RecommendationsResponse',
    fields={'recommendations': ProductSearchSerializer(many=True)},
))
@api_view(['GET'])
@permission_classes([IsCustomerUser])
def get_recommended_products(request):
    """Get recommended products for user"""
    try:
        limit = int(request.query_params.get('limit', 10))
        
        recommendations = UserService.get_recommendations(request.user, limit)
        
        return Response({
            'recommendations': ProductSearchSerializer(recommendations, many=True).data
        })
        
    except Exception as e:
        logger.error(f"Get recommendations error: {e}")
        return Response({'error': 'Failed to get recommendations'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
