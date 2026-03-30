"""
AI engine views mounted as honest wrappers over the live catalog-backed API services.
"""

from __future__ import annotations

import logging

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.ai_services import DatasetVisualSearchService, RealAIService
from apps.api.serializers import (
    BarcodeSearchResultSerializer,
    MarketInsightsSerializer,
    PricePredictionSerializer,
    ProductIdentificationSerializer,
    RankedProductSerializer,
)
from apps.api.views import (
    BarcodeSearchView as _BarcodeSearchView,
    BasketOptimizationView as _BasketOptimizationView,
    GetRankedResultsView as _GetRankedResultsView,
    MarketInsightsView as _MarketInsightsView,
    PricePredictionView as _PricePredictionView,
    ProductIdentificationView as _ProductIdentificationView,
)
from apps.core.runtime_config import DEFAULT_ML_WEIGHTS, ML_WEIGHT_KEYS, get_ml_weights, save_ml_weights
from apps.users.services import SearchService

logger = logging.getLogger(__name__)


class MLRankingView(_GetRankedResultsView):
    """Mirror the mounted ML ranking endpoint under the AI engine namespace."""


class ProductIdentificationView(_ProductIdentificationView):
    """Mirror the mounted visual search endpoint under the AI engine namespace."""


class BarcodeScanningView(_BarcodeSearchView):
    """Mirror the mounted barcode endpoint under the AI engine namespace."""


class BasketOptimizationView(_BasketOptimizationView):
    """Mirror the mounted basket optimization endpoint under the AI engine namespace."""


class PricePredictionView(_PricePredictionView):
    """Mirror the mounted price prediction endpoint under the AI engine namespace."""


class MarketInsightsView(_MarketInsightsView):
    """Mirror the mounted market-insights endpoint under the AI engine namespace."""


class ModelTrainingView(APIView):
    """Refreshes runtime-backed indexes rather than pretending to run offline training jobs."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=inline_serializer(
            name="AiEngineTrainingRequest",
            fields={
                "model_type": serializers.ChoiceField(
                    choices=["ml_ranker", "visual_search", "price_predictor", "all"]
                )
            },
        ),
        responses=inline_serializer(
            name="AiEngineTrainingResponse",
            fields={
                "message": serializers.CharField(),
                "training_results": serializers.DictField(),
            },
        ),
    )
    def post(self, request):
        model_type = str(request.data.get("model_type", "")).strip()
        if not model_type:
            return Response({"error": "Model type required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if model_type in {"visual_search", "all"}:
                DatasetVisualSearchService.dataset_index.__func__.cache_clear()  # type: ignore[attr-defined]
                visual_status = RealAIService.ai_engine_status()["visual_search"]
            else:
                visual_status = None

            training_results = {
                "ml_ranker": {
                    "status": "runtime_weights",
                    "message": "ML ranking is controlled through live runtime weights instead of offline retraining.",
                },
                "price_predictor": {
                    "status": "live_history",
                    "message": "Price prediction uses live price history and sparse-history fallback logic.",
                },
            }
            if visual_status is not None:
                training_results["visual_search"] = {
                    "status": "index_refreshed",
                    "reference_images": visual_status["reference_images"],
                    "category_count": visual_status["category_count"],
                }

            return Response(
                {
                    "message": "Runtime AI services refreshed successfully.",
                    "training_results": training_results,
                }
            )
        except Exception as exc:
            logger.error("Error refreshing AI engine indexes: %s", exc)
            return Response({"error": "Failed to refresh AI engine services"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ModelStatusView(APIView):
    """Expose the live AI status for runtime-backed services."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses=inline_serializer(
            name="AiEngineStatusResponse",
            fields={
                "catalog_loaded": serializers.BooleanField(),
                "ml_weights": serializers.DictField(),
                "visual_search": serializers.DictField(),
                "price_history_records": serializers.IntegerField(),
                "market_sources": serializers.DictField(),
            },
        )
    )
    def get(self, request):
        return Response(RealAIService.ai_engine_status())


@extend_schema(
    request=inline_serializer(
        name="AiEngineNameSearchRequest",
        fields={
            "product_name": serializers.CharField(),
            "top_k": serializers.IntegerField(required=False, min_value=1, max_value=20, default=5),
        },
    ),
    responses=inline_serializer(
        name="AiEngineNameSearchResponse",
        fields={
            "query": serializers.CharField(),
            "matches": RankedProductSerializer(many=True),
            "total_matches": serializers.IntegerField(),
        },
    ),
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def search_by_product_name(request):
    """Search products by name using the live search service."""

    product_name = str(request.data.get("product_name", "")).strip()
    top_k = int(request.data.get("top_k", 5) or 5)
    if not product_name:
        return Response({"error": "Product name required"}, status=status.HTTP_400_BAD_REQUEST)

    products = SearchService.search_products(query=product_name, sort_by="relevance", user=request.user)[:top_k]
    matches = []
    for product in products:
        prices = [
            float(price)
            for price in [product.amazon_price, product.flipkart_price, product.myntra_price]
            if price is not None
        ]
        for offer in product.offers.filter(is_active=True).only("price"):
            if offer.price is not None:
                prices.append(float(offer.price))
        matches.append(
            {
                "id": str(product.id),
                "name": product.name,
                "price": min(prices) if prices else 0.0,
                "distance": 0.0,
                "delivery_time": 24.0,
                "reliability": 1.0,
                "ml_score": 0.0,
                "category": product.category.name if product.category else None,
                "brand": product.brand.name if product.brand else None,
                "image_url": product.image_url,
                "merchant": None,
            }
        )

    return Response({"query": product_name, "matches": matches, "total_matches": len(matches)})


@extend_schema(
    request=inline_serializer(
        name="AiEngineWeightUpdateRequest",
        fields={
            "weights": serializers.DictField(
                child=serializers.FloatField(min_value=0.0),
                help_text="Provide any subset of price, distance, rating, delivery, and reliability.",
            )
        },
    ),
    responses=inline_serializer(
        name="AiEngineWeightUpdateResponse",
        fields={
            "message": serializers.CharField(),
            "new_weights": serializers.DictField(),
        },
    ),
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def update_ranking_weights(request):
    """Update runtime ML weights used by the live ranking service."""

    new_weights = request.data.get("weights")
    if not isinstance(new_weights, dict) or not new_weights:
        return Response({"error": "Weights required"}, status=status.HTTP_400_BAD_REQUEST)

    merged_weights = DEFAULT_ML_WEIGHTS.copy()
    merged_weights.update({key: new_weights[key] for key in new_weights if key in ML_WEIGHT_KEYS})
    saved_weights = save_ml_weights(merged_weights)
    return Response({"message": "Weights updated successfully", "new_weights": saved_weights})


@extend_schema(
    responses=inline_serializer(
        name="AiEngineBarcodeStatsResponse",
        fields={
            "catalog_barcode_products": serializers.IntegerField(),
            "catalog_price_history_rows": serializers.IntegerField(),
            "external_sources": serializers.ListField(),
        },
    )
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_database_statistics(request):
    """Expose real barcode/database statistics."""

    return Response(RealAIService.barcode_dataset_statistics())


@extend_schema(
    responses=inline_serializer(
        name="AiEngineHealthResponse",
        fields={
            "status": serializers.CharField(),
            "services": serializers.DictField(),
            "ml_weights": serializers.DictField(),
        },
    )
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """Health check for the mounted AI engine wrappers."""

    status_payload = RealAIService.ai_engine_status()
    return Response(
        {
            "status": "healthy",
            "services": {
                "ranking": True,
                "visual_search": status_payload["visual_search"]["dataset_available"],
                "barcode_search": True,
                "price_prediction": status_payload["price_history_records"] > 0,
                "market_insights": True,
            },
            "ml_weights": get_ml_weights(),
        }
    )
