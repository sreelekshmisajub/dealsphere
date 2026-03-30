"""
Merchant module views for DealSphere
"""

from decimal import Decimal, InvalidOperation

from rest_framework import status, generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework import serializers
from drf_spectacular.utils import extend_schema, inline_serializer
from django.db import transaction
from django.core.exceptions import ValidationError
import logging

from apps.core.access import IsMerchantUser
from apps.core.models import Merchant, Product, Offer, Order, PriceMatchRequest, UserActivity
from .serializers import (
    MerchantRegistrationSerializer, MerchantProfileSerializer, ProductSerializer, OfferSerializer,
    PriceMatchRequestSerializer, PriceMatchResponseSerializer, MerchantOrderSerializer,
    MerchantDashboardSerializer, MerchantBulkPriceUpdateSerializer,
)
from .services import MerchantService, ProductService
from utils.validators import validate_delivery_time, validate_gstin, validate_price, validate_stock_quantity

logger = logging.getLogger(__name__)


def _to_bool(value, default=True):
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "off", "no"}


def _validate_delivery_cost(value):
    if value in (None, ""):
        return Decimal("0.00")
    try:
        delivery_cost = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError("Invalid delivery cost format")
    if delivery_cost < 0:
        raise ValidationError("Delivery cost cannot be negative")
    return delivery_cost


class MerchantRegistrationView(generics.CreateAPIView):
    """Merchant registration endpoint"""
    permission_classes = [permissions.AllowAny]
    serializer_class = MerchantRegistrationSerializer

    def post(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            user = serializer.save()
            return Response(
                {
                    'message': 'Merchant registration completed successfully. Please log in after admin verification.',
                    'user_email': user.email,
                },
                status=status.HTTP_201_CREATED,
            )
        except (ValidationError, DRFValidationError) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Merchant registration error: {e}")
            return Response({'error': 'Merchant registration failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MerchantProfileView(generics.RetrieveUpdateAPIView):
    """Merchant profile view"""
    serializer_class = MerchantProfileSerializer
    permission_classes = [IsMerchantUser]

    def get_object(self):
        try:
            return self.request.user.merchant_profile
        except Merchant.DoesNotExist:
            raise ValidationError("Merchant profile not found")


class MerchantDashboardView(generics.GenericAPIView):
    """Merchant dashboard summary endpoint."""
    serializer_class = MerchantDashboardSerializer
    permission_classes = [IsMerchantUser]

    def get(self, request, *args, **kwargs):
        try:
            merchant = request.user.merchant_profile
            payload = {
                "merchant": merchant,
                "analytics": MerchantService.get_merchant_analytics(merchant),
                "recent_price_match_requests": PriceMatchRequest.objects.filter(merchant=merchant).order_by("-created_at")[:5],
                "recent_offers": Offer.objects.filter(merchant=merchant).order_by("-updated_at")[:5],
            }
            serializer = self.get_serializer(payload)
            return Response(serializer.data)
        except Merchant.DoesNotExist:
            return Response({"error": "Merchant profile not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Get merchant dashboard error: {e}")
            return Response({"error": "Failed to load merchant dashboard"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class AddProductView(generics.CreateAPIView):
    """Add product for merchant"""
    serializer_class = ProductSerializer
    permission_classes = [IsMerchantUser]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["allow_existing_barcode"] = True
        context["merchant"] = getattr(self.request.user, "merchant_profile", None)
        return context

    def post(self, request, *args, **kwargs):
        try:
            # Check if user is a merchant
            if not request.user.is_merchant:
                return Response({'error': 'User is not a merchant'}, status=status.HTTP_403_FORBIDDEN)

            product_payload = {
                "name": request.data.get("name"),
                "barcode": request.data.get("barcode"),
                "category": request.data.get("category"),
                "brand": request.data.get("brand"),
                "description": request.data.get("description"),
                "image_url": request.data.get("image_url"),
                "amazon_url": request.data.get("amazon_url"),
                "flipkart_url": request.data.get("flipkart_url"),
                "amazon_price": request.data.get("amazon_price"),
                "flipkart_price": request.data.get("flipkart_price"),
            }

            serializer = self.get_serializer(data=product_payload)
            serializer.is_valid(raise_exception=True)

            price = validate_price(request.data.get("price"))
            original_price_raw = request.data.get("original_price")
            original_price = validate_price(original_price_raw) if original_price_raw not in (None, "") else None
            if original_price and original_price < price:
                raise ValidationError("Original price must be greater than or equal to the current price.")

            stock_quantity = validate_stock_quantity(request.data.get("stock_quantity", 1))
            delivery_time_hours = validate_delivery_time(request.data.get("delivery_time_hours", 24))
            delivery_cost = _validate_delivery_cost(request.data.get("delivery_cost"))
            is_active = _to_bool(request.data.get("is_active"), default=True)

            with transaction.atomic():
                merchant = request.user.merchant_profile
                validated = serializer.validated_data
                barcode = validated.get("barcode")

                product = None
                if barcode:
                    product = Product.objects.filter(barcode=barcode).first()

                if product is None:
                    lookup = Product.objects.filter(name__iexact=validated["name"])
                    if validated.get("category"):
                        lookup = lookup.filter(category=validated["category"])
                    if validated.get("brand"):
                        lookup = lookup.filter(brand=validated["brand"])
                    product = lookup.first()

                if product is None:
                    product = serializer.save()
                else:
                    updated_fields = []
                    for field in ["description", "image_url", "amazon_url", "flipkart_url", "amazon_price", "flipkart_price"]:
                        new_value = validated.get(field)
                        if new_value not in (None, "") and not getattr(product, field):
                            setattr(product, field, new_value)
                            updated_fields.append(field)
                    if barcode and product.barcode != barcode:
                        product.barcode = barcode
                        updated_fields.append("barcode")
                    if validated.get("category") and product.category_id != validated["category"].id:
                        product.category = validated["category"]
                        updated_fields.append("category")
                    if validated.get("brand") and product.brand_id != validated["brand"].id:
                        product.brand = validated["brand"]
                        updated_fields.append("brand")
                    if updated_fields:
                        updated_fields.append("updated_at")
                        product.save(update_fields=updated_fields)

                offer, offer_created = Offer.objects.update_or_create(
                    merchant=merchant,
                    product=product,
                    defaults={
                        "price": price,
                        "original_price": original_price,
                        "delivery_time_hours": delivery_time_hours,
                        "delivery_cost": delivery_cost,
                        "stock_quantity": stock_quantity,
                        "is_active": is_active,
                    },
                )

                UserActivity.objects.create(
                    user=request.user,
                    activity_type='product_added' if offer_created else 'offer_updated',
                    product=product,
                    merchant=merchant,
                    metadata={
                        'offer_id': offer.id,
                        'price': float(offer.price),
                        'stock_quantity': offer.stock_quantity,
                        'is_active': offer.is_active,
                    }
                )

                return Response({
                    'message': 'Product listing saved successfully',
                    'product': self.get_serializer(product).data,
                    'offer': OfferSerializer(offer).data,
                    'listing_visible': bool(offer.is_active and offer.price is not None),
                }, status=status.HTTP_201_CREATED)

        except (ValidationError, DRFValidationError) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Add product error: {e}")
            return Response({'error': 'Failed to add product'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class UpdateProductView(generics.UpdateAPIView):
    """Update product for merchant"""
    serializer_class = ProductSerializer
    permission_classes = [IsMerchantUser]

    def get_object(self):
        product_id = self.kwargs.get('product_id')
        try:
            product = Product.objects.get(id=product_id)
            
            # Check if merchant owns this product
            if not Offer.objects.filter(product=product, merchant=self.request.user.merchant_profile).exists():
                raise ValidationError("Merchant doesn't own this product")
            
            return product
        except Product.DoesNotExist:
            raise ValidationError("Product not found")

    def update(self, request, *args, **kwargs):
        try:
            partial = kwargs.pop('partial', False)
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)
            
            with transaction.atomic():
                product = serializer.save()
                
                # Log activity
                UserActivity.objects.create(
                    user=request.user,
                    activity_type='product_updated',
                    product=product,
                    merchant=request.user.merchant_profile
                )
                
                return Response({
                    'message': 'Product updated successfully',
                    'product': serializer.data
                })
                
        except (ValidationError, DRFValidationError) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Update product error: {e}")
            return Response({'error': 'Failed to update product'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CreateOfferView(generics.CreateAPIView):
    """Create offer for product"""
    serializer_class = OfferSerializer
    permission_classes = [IsMerchantUser]

    def post(self, request, *args, **kwargs):
        try:
            # Check if user is a merchant
            if not request.user.is_merchant:
                return Response({'error': 'User is not a merchant'}, status=status.HTTP_403_FORBIDDEN)
            
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            with transaction.atomic():
                # Set merchant from current user
                serializer.validated_data['merchant'] = request.user.merchant_profile
                
                offer = serializer.save()
                
                # Log activity
                UserActivity.objects.create(
                    user=request.user,
                    activity_type='offer_created',
                    product=offer.product,
                    merchant=request.user.merchant_profile,
                    metadata={'offer_price': float(offer.price)}
                )
                
                return Response({
                    'message': 'Offer created successfully',
                    'offer': serializer.data
                }, status=status.HTTP_201_CREATED)
                
        except (ValidationError, DRFValidationError) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Create offer error: {e}")
            return Response({'error': 'Failed to create offer'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class UpdateOfferView(generics.UpdateAPIView):
    """Update offer for merchant"""
    serializer_class = OfferSerializer
    permission_classes = [IsMerchantUser]

    def get_object(self):
        offer_id = self.kwargs.get('offer_id')
        try:
            offer = Offer.objects.get(id=offer_id, merchant=self.request.user.merchant_profile)
            return offer
        except Offer.DoesNotExist:
            raise ValidationError("Offer not found")

    def update(self, request, *args, **kwargs):
        try:
            partial = kwargs.pop('partial', False)
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)
            
            with transaction.atomic():
                offer = serializer.save()
                
                # Log activity
                UserActivity.objects.create(
                    user=request.user,
                    activity_type='offer_updated',
                    product=offer.product,
                    merchant=request.user.merchant_profile,
                    metadata={'offer_price': float(offer.price)}
                )
                
                return Response({
                    'message': 'Offer updated successfully',
                    'offer': serializer.data
                })
                
        except (ValidationError, DRFValidationError) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Update offer error: {e}")
            return Response({'error': 'Failed to update offer'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class PriceMatchRequestsView(generics.ListAPIView):
    """Get price match requests for merchant"""
    serializer_class = PriceMatchRequestSerializer
    permission_classes = [IsMerchantUser]

    def get_queryset(self):
        return PriceMatchRequest.objects.filter(
            merchant=self.request.user.merchant_profile
        ).order_by('-created_at')

class HandlePriceMatchView(generics.UpdateAPIView):
    """Handle price match request"""
    serializer_class = PriceMatchResponseSerializer
    permission_classes = [IsMerchantUser]

    def get_object(self):
        request_id = self.kwargs.get('request_id')
        try:
            price_match = PriceMatchRequest.objects.get(
                id=request_id,
                merchant=self.request.user.merchant_profile,
                status='pending'
            )
            return price_match
        except PriceMatchRequest.DoesNotExist:
            raise ValidationError("Price match request not found")

    def update(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            
            with transaction.atomic():
                price_match = serializer.save()
                
                # Log activity
                UserActivity.objects.create(
                    user=request.user,
                    activity_type='price_match_handled',
                    product=price_match.product,
                    merchant=request.user.merchant_profile,
                    metadata={
                        'status': price_match.status,
                        'requested_price': float(price_match.requested_price),
                        'response_message': price_match.response_message
                    }
                )
                
                return Response({
                    'message': f'Price match request {price_match.status}',
                    'price_match': PriceMatchRequestSerializer(price_match).data
                })
                
        except (ValidationError, DRFValidationError) as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Handle price match error: {e}")
            return Response({'error': 'Failed to handle price match'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class MerchantProductsView(generics.ListAPIView):
    """Get merchant's products"""
    serializer_class = ProductSerializer
    permission_classes = [IsMerchantUser]

    def get_queryset(self):
        merchant = self.request.user.merchant_profile
        return Product.objects.filter(
            offers__merchant=merchant
        ).distinct()

class MerchantOffersView(generics.ListAPIView):
    """Get merchant's offers"""
    serializer_class = OfferSerializer
    permission_classes = [IsMerchantUser]

    def get_queryset(self):
        merchant = self.request.user.merchant_profile
        return Offer.objects.filter(merchant=merchant).order_by('-created_at')


class MerchantOrdersView(generics.ListAPIView):
    """Get merchant orders"""
    serializer_class = MerchantOrderSerializer
    permission_classes = [IsMerchantUser]

    def get_queryset(self):
        merchant = self.request.user.merchant_profile
        return Order.objects.filter(items__merchant=merchant).prefetch_related('items', 'items__product').distinct().order_by('-created_at')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['merchant'] = self.request.user.merchant_profile
        return context

@extend_schema(responses=inline_serializer(
    name='MerchantAnalyticsResponse',
    fields={
        'overview': serializers.DictField(),
        'sales': serializers.DictField(),
        'price_matches': serializers.DictField(),
        'top_products': serializers.ListField(),
        'recent_activities': serializers.ListField(),
        'last_updated': serializers.CharField(),
    },
))
@api_view(['GET'])
@permission_classes([IsMerchantUser])
def merchant_analytics(request):
    """Get merchant analytics"""
    try:
        if not request.user.is_merchant:
            return Response({'error': 'User is not a merchant'}, status=status.HTTP_403_FORBIDDEN)
        
        analytics = MerchantService.get_merchant_analytics(request.user.merchant_profile)
        
        return Response(analytics)
        
    except Exception as e:
        logger.error(f"Get merchant analytics error: {e}")
        return Response({'error': 'Failed to get analytics'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@extend_schema(
    request=inline_serializer(
        name='MerchantBulkPriceUpdateRequest',
        fields={'price_updates': MerchantBulkPriceUpdateSerializer(many=True)},
    ),
    responses=inline_serializer(
        name='MerchantBulkPriceUpdateResponse',
        fields={
            'message': serializers.CharField(),
            'updated_count': serializers.IntegerField(),
            'errors': serializers.ListField(),
        },
    ),
)
@api_view(['POST'])
@permission_classes([IsMerchantUser])
def update_price_bulk(request):
    """Bulk update prices for merchant's offers"""
    try:
        if not request.user.is_merchant:
            return Response({'error': 'User is not a merchant'}, status=status.HTTP_403_FORBIDDEN)
        
        price_updates = request.data.get('price_updates', [])
        
        if not price_updates:
            return Response({'error': 'No price updates provided'}, status=status.HTTP_400_BAD_REQUEST)
        
        updated_count = 0
        errors = []
        
        with transaction.atomic():
            for update in price_updates:
                offer_id = update.get('offer_id')
                new_price = update.get('price')
                
                try:
                    validate_price(new_price)
                    
                    offer = Offer.objects.get(
                        id=offer_id,
                        merchant=request.user.merchant_profile
                    )
                    
                    old_price = offer.price
                    offer.price = new_price
                    offer.save()
                    
                    # Log activity
                    UserActivity.objects.create(
                        user=request.user,
                        activity_type='price_updated',
                        product=offer.product,
                        merchant=request.user.merchant_profile,
                        metadata={
                            'old_price': float(old_price),
                            'new_price': float(new_price)
                        }
                    )
                    
                    updated_count += 1
                    
                except Offer.DoesNotExist:
                    errors.append(f"Offer {offer_id} not found")
                except (ValidationError, DRFValidationError) as e:
                    errors.append(f"Invalid price for offer {offer_id}: {str(e)}")
                except Exception as e:
                    errors.append(f"Error updating offer {offer_id}: {str(e)}")
        
        return Response({
            'message': f'Updated {updated_count} offers',
            'updated_count': updated_count,
            'errors': errors
        })
        
    except Exception as e:
        logger.error(f"Bulk price update error: {e}")
        return Response({'error': 'Failed to update prices'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
