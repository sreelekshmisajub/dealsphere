"""
Services layer for Users app.
"""

import logging
import re
from datetime import timedelta
from difflib import SequenceMatcher
from urllib.parse import parse_qs, unquote, urlparse
from decimal import Decimal
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, F, Q
from django.utils import timezone

from apps.core.catalog_loader import CatalogBootstrapService
from apps.core.models import Cart, CartItem, Notification, Order, OrderItem, Product, UserActivity

logger = logging.getLogger(__name__)

SEARCH_INTENTS = {
    "phone": {
        "aliases": ["phone", "smartphone", "mobile", "iphone", "android", "galaxy", "redmi", "oneplus", "oppo", "vivo", "pixel"],
        "exclude": ["headphone", "headphones", "earphone", "earphones", "earbud", "earbuds", "cable", "charger", "adapter", "case", "cover", "holder", "protector"],
    },
    "laptop": {
        "aliases": ["laptop", "notebook", "macbook", "chromebook"],
        "exclude": ["bag", "sleeve", "stand", "adapter", "charger", "cable", "mouse", "keyboard"],
    },
    "headphone": {
        "aliases": ["headphone", "headphones", "earphone", "earphones", "earbud", "earbuds", "headset"],
        "exclude": ["case", "cover", "holder"],
    },
    "tv": {
        "aliases": ["tv", "television", "smart tv"],
        "exclude": ["remote", "stand", "wall mount", "cable"],
    },
}

COMPARISON_STOPWORDS = {
    "for",
    "with",
    "and",
    "the",
    "pack",
    "combo",
    "men",
    "women",
    "boy",
    "girl",
    "unisex",
    "solid",
    "regular",
    "fit",
    "loose",
    "round",
    "neck",
    "sleeve",
    "sleeves",
    "cotton",
    "inch",
    "inches",
    "gb",
    "ram",
    "storage",
}


def _ensure_catalog_loaded():
    CatalogBootstrapService.ensure_loaded()


def _best_local_offer(product):
    return product.offers.filter(is_active=True).select_related("merchant").order_by("price").first()


def _product_offer_candidates(product):
    candidates = []

    if product.amazon_price is not None:
        candidates.append(
            {
                "source": "amazon",
                "source_name": "Amazon",
                "merchant": None,
                "merchant_id": None,
                "price": Decimal(str(product.amazon_price)),
                "delivery_time_hours": 24,
                "external_url": product.amazon_url,
                "verified": True,
                "rating": float(product.amazon_rating or 0),
            }
        )

    if product.flipkart_price is not None:
        candidates.append(
            {
                "source": "flipkart",
                "source_name": "Flipkart",
                "merchant": None,
                "merchant_id": None,
                "price": Decimal(str(product.flipkart_price)),
                "delivery_time_hours": 48,
                "external_url": product.flipkart_url,
                "verified": True,
                "rating": float(product.flipkart_rating or 0),
            }
        )

    if product.myntra_price is not None:
        candidates.append(
            {
                "source": "myntra",
                "source_name": "Myntra",
                "merchant": None,
                "merchant_id": None,
                "price": Decimal(str(product.myntra_price)),
                "delivery_time_hours": 36,
                "external_url": product.myntra_url,
                "verified": True,
                "rating": float(product.myntra_rating or 0),
            }
        )

    for offer in product.offers.filter(is_active=True).select_related("merchant").order_by("price"):
        candidates.append(
            {
                "source": "local",
                "source_name": offer.merchant.shop_name,
                "merchant": offer.merchant,
                "merchant_id": offer.merchant_id,
                "price": Decimal(str(offer.price)),
                "delivery_time_hours": int(offer.delivery_time_hours),
                "external_url": None,
                "verified": bool(offer.merchant.verified),
                "rating": float(offer.merchant.rating or 0),
            }
        )

    candidates.sort(key=lambda item: (item["price"], item["delivery_time_hours"], item["source_name"]))
    return candidates


def _tokenize_for_comparison(value):
    tokens = []
    for token in _normalize_text(value).split():
        if len(token) < 3 or token in COMPARISON_STOPWORDS:
            continue
        tokens.append(token)
    return tokens


def _catalog_match_score(base_product, candidate_product):
    base_name = _normalize_text(base_product.name)
    candidate_name = _normalize_text(candidate_product.name)
    if not base_name or not candidate_name:
        return 0.0

    base_tokens = set(_tokenize_for_comparison(base_product.name))
    candidate_tokens = set(_tokenize_for_comparison(candidate_product.name))
    overlap = len(base_tokens & candidate_tokens)
    union = len(base_tokens | candidate_tokens) or 1

    token_score = overlap / union
    sequence_score = SequenceMatcher(None, base_name, candidate_name).ratio()
    score = (token_score * 0.65) + (sequence_score * 0.35)

    if base_product.brand_id and candidate_product.brand_id and base_product.brand_id == candidate_product.brand_id:
        score += 0.15
    if base_product.category_id and candidate_product.category_id and base_product.category_id == candidate_product.category_id:
        score += 0.10
    if base_name in candidate_name or candidate_name in base_name:
        score += 0.10

    return round(min(score, 1.0), 4)


def _source_candidate_from_product(product, source, *, match_type="exact", matched_product=None, match_score=None):
    if source == "amazon" and product.amazon_price is not None:
        return {
            "product_id": matched_product.id if matched_product else product.id,
            "product_name": matched_product.name if matched_product else product.name,
            "source": "amazon",
            "source_name": "Amazon",
            "merchant": None,
            "merchant_id": None,
            "price": Decimal(str(product.amazon_price)),
            "original_price": Decimal(str(product.amazon_price)),
            "delivery_time_hours": 24,
            "external_url": product.amazon_url,
            "verified": True,
            "rating": float(product.amazon_rating or 0),
            "match_type": match_type,
            "match_score": match_score,
        }

    if source == "flipkart" and product.flipkart_price is not None:
        return {
            "product_id": matched_product.id if matched_product else product.id,
            "product_name": matched_product.name if matched_product else product.name,
            "source": "flipkart",
            "source_name": "Flipkart",
            "merchant": None,
            "merchant_id": None,
            "price": Decimal(str(product.flipkart_price)),
            "original_price": Decimal(str(product.flipkart_price)),
            "delivery_time_hours": 48,
            "external_url": product.flipkart_url,
            "verified": True,
            "rating": float(product.flipkart_rating or 0),
            "match_type": match_type,
            "match_score": match_score,
        }

    if source == "myntra" and product.myntra_price is not None:
        return {
            "product_id": matched_product.id if matched_product else product.id,
            "product_name": matched_product.name if matched_product else product.name,
            "source": "myntra",
            "source_name": "Myntra",
            "merchant": None,
            "merchant_id": None,
            "price": Decimal(str(product.myntra_price)),
            "original_price": Decimal(str(product.myntra_price)),
            "delivery_time_hours": 36,
            "external_url": product.myntra_url,
            "verified": True,
            "rating": float(product.myntra_rating or 0),
            "match_type": match_type,
            "match_score": match_score,
        }

    if source == "local":
        local_offer = _best_local_offer(product)
        if local_offer:
            return {
                "product_id": matched_product.id if matched_product else product.id,
                "product_name": matched_product.name if matched_product else product.name,
                "source": "local",
                "source_name": local_offer.merchant.shop_name,
                "merchant": local_offer.merchant,
                "merchant_id": local_offer.merchant_id,
                "price": Decimal(str(local_offer.price)),
                "original_price": (
                    Decimal(str(local_offer.original_price))
                    if local_offer.original_price is not None
                    else Decimal(str(local_offer.price))
                ),
                "delivery_time_hours": int(local_offer.delivery_time_hours or 24),
                "external_url": None,
                "verified": bool(local_offer.merchant.verified),
                "rating": float(local_offer.merchant.rating or 0),
                "match_type": match_type,
                "match_score": match_score,
            }

    return None


def _resolve_candidate(product, source=None, merchant_id=None):
    candidates = _product_offer_candidates(product)
    if not candidates:
        return None

    normalized_source = (source or "").strip().lower()
    if normalized_source:
        filtered = [candidate for candidate in candidates if candidate["source"] == normalized_source]
        if merchant_id:
            filtered = [candidate for candidate in filtered if str(candidate["merchant_id"]) == str(merchant_id)]
        if filtered:
            return filtered[0]

    if merchant_id:
        filtered = [candidate for candidate in candidates if str(candidate["merchant_id"]) == str(merchant_id)]
        if filtered:
            return filtered[0]

    return candidates[0]


def _effective_price(product):
    prices = []
    local_offer = _best_local_offer(product)
    if local_offer:
        prices.append(float(local_offer.price))
    if product.amazon_price is not None:
        prices.append(float(product.amazon_price))
    if product.flipkart_price is not None:
        prices.append(float(product.flipkart_price))
    if product.myntra_price is not None:
        prices.append(float(product.myntra_price))
    return min(prices) if prices else None


def _effective_rating(product):
    ratings = []
    if product.amazon_rating is not None:
        ratings.append(float(product.amazon_rating))
    if product.flipkart_rating is not None:
        ratings.append(float(product.flipkart_rating))
    if product.myntra_rating is not None:
        ratings.append(float(product.myntra_rating))
    local_offer = _best_local_offer(product)
    if local_offer and local_offer.merchant.rating is not None:
        ratings.append(float(local_offer.merchant.rating))
    return max(ratings) if ratings else 0.0


def _is_searchable(product):
    return _effective_price(product) is not None


def _normalize_text(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _extract_query_text(query):
    raw_query = unquote(str(query or "").strip())
    if not raw_query:
        return ""

    if raw_query.startswith(("http://", "https://")):
        parsed = urlparse(raw_query)
        query_text = " ".join(
            value
            for values in parse_qs(parsed.query).values()
            for value in values
        )
        raw_query = " ".join(part for part in [parsed.path.replace("-", " ").replace("_", " "), query_text] if part)

    return _normalize_text(raw_query)


def _contains_term(text, term):
    normalized_term = _normalize_text(term)
    if not normalized_term:
        return False
    if " " in normalized_term:
        return normalized_term in text
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])", text))


def _search_intent(normalized_query, tokens):
    for key, config in SEARCH_INTENTS.items():
        if key in tokens or any(alias in normalized_query for alias in config["aliases"]):
            return config
    return None


def _product_search_blob(product):
    return _normalize_text(
        " ".join(
            part
            for part in [
                product.name,
                product.brand.name if product.brand else "",
                product.category.name if product.category else "",
                product.description or "",
            ]
            if part
        )
    )


def _matches_query(product, normalized_query):
    if not normalized_query:
        return True

    tokens = [token for token in normalized_query.split() if token]
    if not tokens:
        return True

    name = _normalize_text(product.name)
    brand = _normalize_text(product.brand.name if product.brand else "")
    category = _normalize_text(product.category.name if product.category else "")
    intent = _search_intent(normalized_query, tokens)

    if intent:
        alias_match = any(
            _contains_term(name, alias) or _contains_term(category, alias) or _contains_term(brand, alias)
            for alias in intent["aliases"]
        )
        excluded = any(
            _contains_term(name, term) or _contains_term(category, term) or _contains_term(brand, term)
            for term in intent["exclude"]
        )
        if not alias_match or excluded:
            return False
        return True

    return all(
        _contains_term(name, token) or _contains_term(category, token) or _contains_term(brand, token)
        for token in tokens
    )


def _relevance_score(product, normalized_query):
    if not normalized_query:
        return 0

    tokens = [token for token in normalized_query.split() if token]
    name = _normalize_text(product.name)
    brand = _normalize_text(product.brand.name if product.brand else "")
    category = _normalize_text(product.category.name if product.category else "")
    intent = _search_intent(normalized_query, tokens)
    score = 0

    if intent:
        for alias in intent["aliases"]:
            if _contains_term(name, alias):
                score += 120
            elif _contains_term(category, alias):
                score += 90
            elif _contains_term(brand, alias):
                score += 70
        for term in intent["exclude"]:
            if _contains_term(name, term) or _contains_term(category, term) or _contains_term(brand, term):
                score -= 200
    else:
        if name == normalized_query:
            score += 200
        if normalized_query and normalized_query in name:
            score += 120
        for token in tokens:
            if _contains_term(name, token):
                score += 60
            elif _contains_term(category, token):
                score += 35
            elif _contains_term(brand, token):
                score += 25

    score += min(_effective_rating(product) * 5, 25)
    return score


class UserService:
    """User service for business logic."""

    @staticmethod
    def get_recommendations(user, limit=10):
        try:
            _ensure_catalog_loaded()

            recent_activities = UserActivity.objects.filter(
                user=user,
                activity_type__in=["search", "product_view", "add_to_cart"],
                created_at__gte=timezone.now() - timedelta(days=30),
            ).select_related("product", "product__category", "product__brand")

            preferred_categories = {activity.product.category for activity in recent_activities if activity.product and activity.product.category}
            preferred_brands = {activity.product.brand for activity in recent_activities if activity.product and activity.product.brand}

            queryset = Product.objects.select_related("category", "brand").prefetch_related("offers__merchant")
            if preferred_categories:
                queryset = queryset.filter(category__in=preferred_categories)
            if preferred_brands:
                queryset = queryset.filter(brand__in=preferred_brands)

            products = [product for product in queryset.distinct() if _is_searchable(product)]

            if hasattr(user, "cart") and user.cart:
                cart_product_ids = set(user.cart.items.values_list("product_id", flat=True))
                products = [product for product in products if product.id not in cart_product_ids]

            products.sort(key=lambda product: (-_effective_rating(product), _effective_price(product) or float("inf"), product.name.lower()))
            return products[:limit]

        except Exception as e:
            logger.error(f"Error getting recommendations: {e}")
            return []

    @staticmethod
    def track_activity(user, activity_type, product=None, merchant=None, metadata=None):
        try:
            UserActivity.objects.create(
                user=user,
                activity_type=activity_type,
                product=product,
                merchant=merchant,
                metadata=metadata or {},
            )
        except Exception as e:
            logger.error(f"Error tracking activity: {e}")


class SearchService:
    """Search service for real products."""

    @staticmethod
    def search_products(query, category=None, min_price=None, max_price=None, sort_by="relevance", user=None):
        try:
            _ensure_catalog_loaded()

            queryset = Product.objects.select_related("category", "brand").prefetch_related("offers__merchant")
            normalized_query = _extract_query_text(query)

            if category:
                queryset = queryset.filter(category__name__icontains=category)

            products = [product for product in queryset.distinct() if _is_searchable(product)]
            if normalized_query:
                products = [product for product in products if _matches_query(product, normalized_query)]

            min_price_value = float(min_price) if min_price not in (None, "") else None
            max_price_value = float(max_price) if max_price not in (None, "") else None

            if min_price_value is not None:
                products = [product for product in products if (_effective_price(product) or 0) >= min_price_value]
            if max_price_value is not None:
                products = [product for product in products if (_effective_price(product) or float("inf")) <= max_price_value]

            if sort_by == "price_low":
                products.sort(key=lambda product: (_effective_price(product) or float("inf"), product.name.lower()))
            elif sort_by == "price_high":
                products.sort(key=lambda product: (_effective_price(product) or 0, product.name.lower()), reverse=True)
            elif sort_by == "rating":
                products.sort(key=lambda product: (_effective_rating(product), -(_effective_price(product) or 0)), reverse=True)
            elif sort_by == "newest":
                products.sort(key=lambda product: product.created_at, reverse=True)
            else:
                products.sort(
                    key=lambda product: (
                        -_relevance_score(product, normalized_query),
                        _effective_price(product) or float("inf"),
                        product.name.lower(),
                    )
                )

            if user and getattr(user, "is_authenticated", False):
                UserService.track_activity(
                    user=user,
                    activity_type="search",
                    metadata={
                        "query": query,
                        "category": category,
                        "min_price": min_price,
                        "max_price": max_price,
                        "sort_by": sort_by,
                        "results_count": len(products),
                    },
                )

            return products

        except Exception as e:
            logger.error(f"Error searching products: {e}")
            return []

    @staticmethod
    def get_similar_products(product_id, limit=5):
        try:
            _ensure_catalog_loaded()
            product = Product.objects.select_related("category", "brand").get(id=product_id)
            queryset = Product.objects.select_related("category", "brand").prefetch_related("offers__merchant").filter(
                Q(category=product.category) | Q(brand=product.brand)
            ).exclude(id=product.id)

            products = [item for item in queryset.distinct() if _is_searchable(item)]
            products.sort(
                key=lambda item: (
                    int(item.category_id == product.category_id),
                    int(item.brand_id == product.brand_id),
                    -_effective_rating(item),
                    _effective_price(item) or float("inf"),
                ),
                reverse=True,
            )
            return products[:limit]

        except Product.DoesNotExist:
            return []
        except Exception as e:
            logger.error(f"Error getting similar products: {e}")
            return []

    @staticmethod
    def get_trending_products(limit=24):
        try:
            _ensure_catalog_loaded()
            base_qs = (
                Product.objects.select_related("category", "brand")
                .prefetch_related("offers__merchant")
                .annotate(offer_count=Count("offers"))
            )

            # Online-sourced products first (have Amazon/Flipkart/Myntra prices)
            online_qs = (
                base_qs.filter(
                    Q(amazon_price__isnull=False)
                    | Q(flipkart_price__isnull=False)
                    | Q(myntra_price__isnull=False)
                ).order_by(F("amazon_rating").desc(nulls_last=True), "-offer_count", "-created_at")
            )
            online_products = [p for p in online_qs if _is_searchable(p)]

            if len(online_products) >= limit:
                return online_products[:limit]

            # Fill remaining slots with local-only products
            online_ids = {p.id for p in online_products}
            local_qs = (
                base_qs.exclude(id__in=online_ids)
                .order_by("-offer_count", "-created_at")
            )
            local_products = [p for p in local_qs if _is_searchable(p)]
            return (online_products + local_products)[:limit]

        except Exception as e:
            logger.error(f"Error getting trending products: {e}")
            return []


class ProductService:
    """Product service for business logic."""

    @staticmethod
    def get_product_details(product_id, user=None):
        try:
            _ensure_catalog_loaded()
            product = Product.objects.select_related("category", "brand").prefetch_related("offers__merchant", "price_history").get(id=product_id)
            offers = product.offers.filter(is_active=True).select_related("merchant").order_by("price")
            price_history = product.price_history.order_by("-created_at")[:30]

            if user and getattr(user, "is_authenticated", False):
                UserService.track_activity(user=user, activity_type="product_view", product=product)

            return {"product": product, "offers": offers, "price_history": price_history}

        except Product.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Error getting product details: {e}")
            return None

    @staticmethod
    def get_price_comparison(product_id):
        try:
            _ensure_catalog_loaded()
            product = Product.objects.select_related("category", "brand").prefetch_related("offers__merchant").get(id=product_id)

            comparison = {
                "amazon": {
                    "price": product.amazon_price,
                    "url": product.amazon_url,
                    "rating": product.amazon_rating,
                },
                "flipkart": {
                    "price": product.flipkart_price,
                    "url": product.flipkart_url,
                    "rating": product.flipkart_rating,
                },
                "myntra": {
                    "price": product.myntra_price,
                    "url": product.myntra_url,
                    "rating": product.myntra_rating,
                },
                "local_stores": [],
            }

            for offer in product.offers.filter(is_active=True).select_related("merchant").order_by("price"):
                comparison["local_stores"].append(
                    {
                        "merchant": offer.merchant.shop_name,
                        "price": offer.price,
                        "delivery_time_hours": offer.delivery_time_hours,
                        "delivery_cost": offer.delivery_cost,
                        "discount_percentage": offer.discount_percentage,
                        "rating": offer.merchant.rating,
                    }
                )

            return comparison

        except Product.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"Error getting price comparison: {e}")
            return None

    @staticmethod
    def get_comparison_candidates(product_id):
        try:
            _ensure_catalog_loaded()
            product = Product.objects.select_related("category", "brand").prefetch_related("offers__merchant").get(id=product_id)
            exact_candidates = []
            for candidate in _product_offer_candidates(product):
                enriched = dict(candidate)
                enriched["product_id"] = product.id
                enriched["product_name"] = product.name
                enriched["match_type"] = "exact"
                enriched["match_score"] = 1.0
                exact_candidates.append(enriched)

            present_sources = {candidate["source"] for candidate in exact_candidates}
            missing_sources = [
                source for source in ("amazon", "flipkart", "myntra", "local") if source not in present_sources
            ]

            related_candidates = []
            if missing_sources:
                related_candidates = ProductService.get_related_source_candidates(product, missing_sources)

            candidates = exact_candidates + related_candidates
            candidates.sort(
                key=lambda item: (
                    item["price"],
                    0 if item["match_type"] == "exact" else 1,
                    -(item["match_score"] or 0),
                    item["source_name"],
                )
            )
            return candidates
        except Product.DoesNotExist:
            return []
        except Exception as e:
            logger.error(f"Error getting comparison candidates: {e}")
            return []

    @staticmethod
    def get_related_source_candidates(product, target_sources=None):
        target_sources = tuple(target_sources or ())
        if not target_sources:
            return []

        candidate_filters = Q()
        if product.category_id:
            candidate_filters |= Q(category_id=product.category_id)
        if product.brand_id:
            candidate_filters |= Q(brand_id=product.brand_id)

        for token in list(dict.fromkeys(_tokenize_for_comparison(product.name)))[:8]:
            candidate_filters |= Q(name__icontains=token)

        queryset = Product.objects.select_related("category", "brand").prefetch_related("offers__merchant").exclude(id=product.id)
        if candidate_filters:
            queryset = queryset.filter(candidate_filters)

        best_by_source = {}
        for candidate_product in queryset.iterator():
            score = _catalog_match_score(product, candidate_product)
            if score < 0.42:
                continue

            for source in target_sources:
                source_candidate = _source_candidate_from_product(
                    candidate_product,
                    source,
                    match_type="catalog_match",
                    matched_product=candidate_product,
                    match_score=score,
                )
                if not source_candidate:
                    continue

                existing = best_by_source.get(source)
                if existing is None:
                    best_by_source[source] = source_candidate
                    continue

                if score > (existing.get("match_score") or 0):
                    best_by_source[source] = source_candidate
                    continue

                if score == (existing.get("match_score") or 0) and source_candidate["price"] < existing["price"]:
                    best_by_source[source] = source_candidate

        return list(best_by_source.values())


class CartOrderService:
    """Shared cart and checkout logic for real catalog-backed flows."""

    @staticmethod
    def payment_configuration():
        config = getattr(settings, "PAYMENT_SETTINGS", {})
        return {
            "upi_id": config.get("upi_id", ""),
            "upi_name": config.get("upi_name", "DealSphere"),
            "gateway_url": config.get("gateway_url", ""),
            "gateway_name": config.get("gateway_name", "Online Gateway"),
            "upi_enabled": bool(config.get("upi_enabled")),
            "gateway_enabled": bool(config.get("gateway_enabled")),
        }

    @staticmethod
    def payment_choices(has_local_items, has_external_items):
        config = CartOrderService.payment_configuration()
        choices = []
        if has_external_items and not has_local_items:
            choices.append(
                {
                    "value": "external_redirect",
                    "label": "External Redirect",
                    "note": "Open Amazon, Flipkart, or Myntra checkout pages for the selected items.",
                    "enabled": True,
                }
            )
            return choices

        if has_local_items and not has_external_items:
            # Prioritize UPI as requested
            if config["upi_enabled"]:
                choices.append(
                    {
                        "value": "upi",
                        "label": "UPI",
                        "note": f"Generate a UPI payment link to {config['upi_name']}.",
                        "enabled": True,
                    }
                )

            choices.extend(
                [
                    {
                        "value": "cash_on_delivery",
                        "label": "Cash on Delivery",
                        "note": "Create a local-merchant order with payment due on delivery.",
                        "enabled": True,
                    },
                    {
                        "value": "pay_in_store",
                        "label": "Pay in Store",
                        "note": "Reserve the order and pay directly at the merchant location.",
                        "enabled": True,
                    },
                ]
            )

            # Keep UPI placeholder if not enabled (moved from above if preferred, but usually we just skip)
            if not config["upi_enabled"]:
                choices.append(
                    {
                        "value": "upi",
                        "label": "UPI",
                        "note": "UPI option is available after a UPI payee ID is configured.",
                        "enabled": False,
                    }
                )

            choices.append(
                {
                    "value": "online_gateway",
                    "label": config["gateway_name"],
                    "note": (
                        "Redirect to the configured online payment gateway."
                        if config["gateway_enabled"]
                        else "Online prepaid option is available after a payment gateway URL is configured."
                    ),
                    "enabled": config["gateway_enabled"],
                }
            )
        return choices


    @staticmethod
    def _payment_link(payment_method, order, total_amount, user):
        config = CartOrderService.payment_configuration()
        reference = f"DS-{str(order.id).split('-')[0].upper()}"

        if payment_method == "upi":
            if not config["upi_enabled"]:
                raise ValidationError("UPI payment is not configured yet.")
            params = urlencode(
                {
                    "pa": config["upi_id"],
                    "pn": config["upi_name"],
                    "tr": reference,
                    "tn": f"DealSphere order {order.id}",
                    "am": f"{float(total_amount):.2f}",
                    "cu": "INR",
                }
            )
            return reference, f"upi://pay?{params}"

        if payment_method == "online_gateway":
            if not config["gateway_enabled"]:
                raise ValidationError("Online payment gateway is not configured yet.")
            params = urlencode(
                {
                    "order_id": str(order.id),
                    "reference": reference,
                    "amount": f"{float(total_amount):.2f}",
                    "currency": "INR",
                    "customer_email": user.email,
                    "customer_name": user.get_full_name() or user.username,
                }
            )
            separator = "&" if "?" in config["gateway_url"] else "?"
            return reference, f"{config['gateway_url']}{separator}{params}"

        return reference, None

    @staticmethod
    def add_to_cart(user, product_id, quantity=1, source=None, merchant_id=None):
        _ensure_catalog_loaded()
        product = Product.objects.select_related("category", "brand").prefetch_related("offers__merchant").get(id=product_id)
        candidate = _resolve_candidate(product, source=source, merchant_id=merchant_id)
        if not candidate:
            raise ValidationError("No active price source is available for this product.")

        quantity = int(quantity)
        if quantity < 1:
            raise ValidationError("Quantity must be at least 1.")

        cart, _ = Cart.objects.get_or_create(user=user)
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={
                "quantity": quantity,
                "merchant": candidate["merchant"],
                "selected_source": candidate["source"],
                "selected_source_name": candidate["source_name"],
                "unit_price_snapshot": candidate["price"],
                "delivery_time_hours": candidate["delivery_time_hours"],
            },
        )

        if not created:
            cart_item.quantity += quantity
            cart_item.merchant = candidate["merchant"]
            cart_item.selected_source = candidate["source"]
            cart_item.selected_source_name = candidate["source_name"]
            cart_item.unit_price_snapshot = candidate["price"]
            cart_item.delivery_time_hours = candidate["delivery_time_hours"]
            cart_item.save()

        UserService.track_activity(
            user=user,
            activity_type="add_to_cart",
            product=product,
            merchant=candidate["merchant"],
            metadata={
                "quantity": quantity,
                "source": candidate["source"],
                "source_name": candidate["source_name"],
                "unit_price": float(candidate["price"]),
            },
        )
        return cart_item, candidate

    @staticmethod
    def update_cart_item(user, product_id, quantity):
        cart = Cart.objects.get(user=user)
        item = CartItem.objects.select_related("product", "merchant").get(cart=cart, product_id=product_id)
        quantity = int(quantity)
        if quantity < 1:
            item.delete()
            return None
        item.quantity = quantity
        item.save()
        return item

    @staticmethod
    def cart_items_with_totals(user):
        cart, _ = Cart.objects.get_or_create(user=user)
        items = list(cart.items.select_related("product", "product__category", "merchant").order_by("-added_at"))
        total = Decimal("0.00")
        total_items = 0
        for item in items:
            if item.unit_price_snapshot is None:
                candidate = _resolve_candidate(item.product, source=item.selected_source, merchant_id=item.merchant_id)
                if candidate:
                    item.unit_price_snapshot = candidate["price"]
                    item.selected_source_name = candidate["source_name"]
                    item.delivery_time_hours = candidate["delivery_time_hours"]
                    item.merchant = candidate["merchant"]
                    item.save(update_fields=["unit_price_snapshot", "selected_source_name", "delivery_time_hours", "merchant"])
            total += (item.unit_price_snapshot or Decimal("0.00")) * item.quantity
            total_items += item.quantity
        return cart, items, total.quantize(Decimal("0.01")), total_items

    @staticmethod
    def create_order_from_cart(user, delivery_address, payment_method):
        if not delivery_address:
            raise ValidationError("Delivery address is required.")

        cart, items, total, total_items = CartOrderService.cart_items_with_totals(user)
        if not items:
            raise ValidationError("Your cart is empty.")

        payment_method = (payment_method or "").strip().lower()
        if payment_method not in {"cash_on_delivery", "pay_in_store", "upi", "online_gateway", "external_redirect"}:
            raise ValidationError("Select a valid payment method.")

        has_external_items = any(item.selected_source in {"amazon", "flipkart", "myntra"} for item in items)
        has_local_items = any(item.selected_source == "local" for item in items)

        if has_external_items and has_local_items:
            raise ValidationError(
                "Checkout local-store items separately from Amazon, Flipkart, or Myntra items so payment routing stays correct."
            )
        if has_external_items and payment_method != "external_redirect":
            raise ValidationError("Use external redirect for carts that contain Amazon, Flipkart, or Myntra items.")
        if has_local_items and payment_method == "external_redirect" and not has_external_items:
            raise ValidationError("External redirect is only available for online-source items.")
        if has_external_items and payment_method in {"upi", "online_gateway"}:
            raise ValidationError("UPI and online gateway payments are only available for local-store orders.")

        order_status = "confirmed" if payment_method in {"cash_on_delivery", "pay_in_store"} else "pending"
        payment_status = "redirect_required" if payment_method in {"external_redirect", "upi", "online_gateway"} else "pending"

        with transaction.atomic():
            order = Order.objects.create(
                user=user,
                total_amount=total,
                delivery_cost=Decimal("0.00"),
                status=order_status,
                payment_method=payment_method,
                payment_status=payment_status,
                delivery_address=delivery_address,
            )

            payment_reference, payment_link = CartOrderService._payment_link(payment_method, order, total, user)
            order.payment_reference = payment_reference
            order.payment_link = payment_link
            order.save(update_fields=["payment_reference", "payment_link"])

            external_links = []
            merchant_names = set()
            for item in items:
                external_url = None
                if item.selected_source == "amazon":
                    external_url = item.product.amazon_url
                elif item.selected_source == "flipkart":
                    external_url = item.product.flipkart_url
                elif item.selected_source == "myntra":
                    external_url = item.product.myntra_url

                order_item = OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    merchant=item.merchant if item.selected_source == "local" else None,
                    source=item.selected_source,
                    source_name=item.selected_source_name,
                    external_url=external_url,
                    quantity=item.quantity,
                    price=item.unit_price_snapshot or Decimal("0.00"),
                    delivery_time_hours=item.delivery_time_hours,
                )

                if order_item.merchant:
                    merchant_names.add(order_item.merchant.shop_name)
                    Notification.objects.create(
                        user=order_item.merchant.user,
                        title="New customer order",
                        message=f"Order {order.id} includes {order_item.product.name}.",
                        notification_type="order_update",
                    )

                if external_url:
                    external_links.append(
                        {
                            "product_id": order_item.product_id,
                            "product_name": order_item.product.name,
                            "source": order_item.source_name,
                            "url": external_url,
                        }
                    )

            Notification.objects.create(
                user=user,
                title="Order created",
                message=f"Order {order.id} was created with {total_items} item(s).",
                notification_type="order_update",
            )

            UserService.track_activity(
                user=user,
                activity_type="order_created",
                metadata={
                    "order_id": str(order.id),
                    "payment_method": payment_method,
                    "payment_status": payment_status,
                    "total_amount": float(total),
                    "merchant_count": len(merchant_names),
                    "external_items": len(external_links),
                },
            )

            cart.items.all().delete()

        return order, external_links
