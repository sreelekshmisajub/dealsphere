from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
import logging
from pathlib import Path
from types import SimpleNamespace

logger = logging.getLogger(__name__)


from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout, update_session_auth_hash
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.db import OperationalError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Avg, Count, F, Q, Sum
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import TemplateView
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie


from apps.admin_panel.services import AdminService
from apps.api.ai_services import RealAIService
from apps.api.external_feeds import RealTimePriceService
from apps.core.catalog_loader import CatalogBootstrapService
from apps.core.models import (
    Cart,
    CartItem,
    Brand,
    Category,
    Merchant,
    Notification,
    Offer,
    Order,
    OrderItem,
    PriceMatchRequest,
    Product,
    UserActivity,
)
from apps.core.registration import create_customer_account, create_merchant_account
from apps.core.runtime_config import get_ml_weights_metadata, save_ml_weights
from apps.merchants.services import MerchantService, ProductService as MerchantProductService
from apps.users.services import CartOrderService, ProductService, SearchService, UserService
from utils.validators import (
    validate_barcode,
    validate_delivery_time,
    validate_gstin,
    validate_location,
    validate_phone_number,
    validate_price,
    validate_stock_quantity,
    validate_strong_password,
)


User = get_user_model()


def _empty_page(per_page=12):
    return Paginator([], per_page).get_page(1)


def _to_float(value):
    if value in (None, ""):
        return None
    return float(value)


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def _status_progress(status: str) -> float:
    return {
        "pending": 0.08,
        "confirmed": 0.22,
        "processing": 0.42,
        "shipped": 0.76,
        "delivered": 1.0,
        "cancelled": 0.0,
    }.get((status or "").strip().lower(), 0.12)


def _interpolate_position(start_lat, start_lng, end_lat, end_lng, progress):
    return (
        round(start_lat + ((end_lat - start_lat) * progress), 6),
        round(start_lng + ((end_lng - start_lng) * progress), 6),
    )


def _build_order_delivery_map(order, user, index):
    local_items = [
        item
        for item in order.items.all()
        if item.source == "local" and item.merchant_id and item.merchant
    ]
    if not local_items:
        return SimpleNamespace(
            available=False,
            reason="Live map is available for local merchant deliveries only.",
        )

    customer_lat = _to_float(getattr(user, "location_lat", None))
    customer_lng = _to_float(getattr(user, "location_lng", None))
    if customer_lat is None or customer_lng is None:
        return SimpleNamespace(
            available=False,
            reason="Add your saved location in your profile to view the live delivery map.",
        )

    merchant_points = []
    seen_merchants = set()
    for item in local_items:
        merchant = item.merchant
        lat = _to_float(getattr(merchant, "location_lat", None))
        lng = _to_float(getattr(merchant, "location_lng", None))
        if lat is None or lng is None:
            continue
        merchant_key = (merchant.id, lat, lng)
        if merchant_key in seen_merchants:
            continue
        seen_merchants.add(merchant_key)
        merchant_points.append(
            {
                "merchant_id": merchant.id,
                "label": merchant.shop_name,
                "lat": lat,
                "lng": lng,
            }
        )

    if not merchant_points:
        return SimpleNamespace(
            available=False,
            reason="Merchant location is not available for this delivery yet.",
        )

    if order.status == "cancelled":
        return SimpleNamespace(
            available=False,
            reason="This order was cancelled, so live delivery tracking is not available.",
        )

    primary_item = min(local_items, key=lambda item: int(item.delivery_time_hours or 24))
    primary_origin = next(
        (
            point
            for point in merchant_points
            if point["merchant_id"] == getattr(primary_item.merchant, "id", None)
        ),
        merchant_points[0],
    )

    max_eta_hours = max(int(item.delivery_time_hours or 24) for item in local_items) or 24
    elapsed_hours = max((timezone.now() - order.created_at).total_seconds() / 3600, 0)
    time_progress = _clamp(elapsed_hours / max_eta_hours if max_eta_hours else 0, 0.0, 0.98)
    progress = 1.0 if order.status == "delivered" else _clamp(max(_status_progress(order.status), time_progress))
    courier_lat, courier_lng = _interpolate_position(
        primary_origin["lat"],
        primary_origin["lng"],
        customer_lat,
        customer_lng,
        progress,
    )

    remaining_hours = 0.0 if order.status == "delivered" else round(max(max_eta_hours - elapsed_hours, 0), 1)
    if order.status == "delivered":
        eta_label = "Delivered"
        status_copy = "Delivery completed"
    elif progress >= 0.72:
        eta_label = f"{remaining_hours:.1f} hrs remaining" if remaining_hours else "Arriving soon"
        status_copy = "Courier is on the way"
    elif progress >= 0.35:
        eta_label = f"{remaining_hours:.1f} hrs remaining" if remaining_hours else "Preparing dispatch"
        status_copy = "Order is being packed for delivery"
    else:
        eta_label = f"{remaining_hours:.1f} hrs remaining" if remaining_hours else "Queued"
        status_copy = "Merchant is preparing the order"

    payload = {
        "customer": {
            "label": "Your saved location",
            "lat": customer_lat,
            "lng": customer_lng,
        },
        "origins": merchant_points,
        "primary_origin": primary_origin,
        "courier": {
            "label": "Estimated courier position",
            "lat": courier_lat,
            "lng": courier_lng,
        },
        "progress": round(progress, 3),
        "progress_percent": int(round(progress * 100)),
        "status": order.status,
        "route": [
            [primary_origin["lat"], primary_origin["lng"]],
            [courier_lat, courier_lng],
            [customer_lat, customer_lng],
        ],
    }

    return SimpleNamespace(
        available=True,
        script_id=f"order-map-data-{index}",
        map_id=f"order-map-{index}",
        payload=payload,
        progress_percent=payload["progress_percent"],
        eta_label=eta_label,
        status_copy=status_copy,
        note="Map uses your saved profile coordinates and local merchant locations.",
        additional_origin_count=max(len(merchant_points) - 1, 0),
    )


def _discount_percentage(price, original_price):
    if price in (None, "") or original_price in (None, ""):
        return None
    price_decimal = Decimal(str(price))
    original_decimal = Decimal(str(original_price))
    if original_decimal <= 0 or original_decimal <= price_decimal:
        return None
    return round(float(((original_decimal - price_decimal) / original_decimal) * 100), 2)


def _retailer_search_url(source: str, product_name: str) -> str:
    """Return a retailer search URL for a product name when a direct URL is not stored."""
    from urllib.parse import quote as _quote
    q = _quote(product_name.strip(), safe="")
    if source == "amazon":
        return f"https://www.amazon.in/s?k={q}"
    if source == "flipkart":
        return f"https://www.flipkart.com/search?q={q}"
    if source == "myntra":
        return f"https://www.myntra.com/{q.replace('%20', '-')}"
    return ""


def _best_offer_payload(product):
    offer = product.offers.filter(is_active=True).select_related("merchant").order_by("price").first()
    if offer:
        return SimpleNamespace(
            price=float(offer.price),
            original_price=float(offer.original_price) if offer.original_price else None,
            merchant=offer.merchant.shop_name,
            merchant_id=offer.merchant_id,
            delivery_time_hours=offer.delivery_time_hours,
            source="local",
            source_icon="fas fa-store",
            verified=offer.merchant.verified,
            discount_percentage=_discount_percentage(offer.price, offer.original_price),
            external_url=None,
        )

    pname = product.name or ""
    online_sources = []
    if product.amazon_price is not None:
        online_sources.append(
            SimpleNamespace(
                price=float(product.amazon_price),
                original_price=float(product.amazon_price),
                merchant="Amazon",
                merchant_id=None,
                delivery_time_hours=24,
                source="amazon",
                source_icon="fab fa-amazon",
                verified=True,
                discount_percentage=None,
                external_url=product.amazon_url or _retailer_search_url("amazon", pname),
            )
        )
    if product.flipkart_price is not None:
        online_sources.append(
            SimpleNamespace(
                price=float(product.flipkart_price),
                original_price=float(product.flipkart_price),
                merchant="Flipkart",
                merchant_id=None,
                delivery_time_hours=48,
                source="flipkart",
                source_icon="fas fa-bag-shopping",
                verified=True,
                discount_percentage=None,
                external_url=product.flipkart_url or _retailer_search_url("flipkart", pname),
            )
        )
    if product.myntra_price is not None:
        online_sources.append(
            SimpleNamespace(
                price=float(product.myntra_price),
                original_price=float(product.myntra_price),
                merchant="Myntra",
                merchant_id=None,
                delivery_time_hours=36,
                source="myntra",
                source_icon="fas fa-shirt",
                verified=True,
                discount_percentage=None,
                external_url=product.myntra_url or _retailer_search_url("myntra", pname),
            )
        )

    if online_sources:
        return min(online_sources, key=lambda item: (item.price, item.delivery_time_hours, item.merchant))

    return None


def _online_baseline_price(product):
    prices = [
        value
        for value in [_to_float(product.amazon_price), _to_float(product.flipkart_price), _to_float(product.myntra_price)]
        if value is not None
    ]
    return min(prices) if prices else None


def _online_offer_payload(product):
    """Return the cheapest online offer (Amazon / Flipkart / Myntra) for a product."""
    pname = product.name or ""
    sources = []
    if product.amazon_price is not None:
        sources.append(SimpleNamespace(
            price=float(product.amazon_price),
            merchant="Amazon", source="amazon",
            source_icon="fab fa-amazon",
            delivery_time_hours=24,
            external_url=product.amazon_url or _retailer_search_url("amazon", pname),
        ))
    if product.flipkart_price is not None:
        sources.append(SimpleNamespace(
            price=float(product.flipkart_price),
            merchant="Flipkart", source="flipkart",
            source_icon="fas fa-bag-shopping",
            delivery_time_hours=48,
            external_url=product.flipkart_url or _retailer_search_url("flipkart", pname),
        ))
    if product.myntra_price is not None:
        sources.append(SimpleNamespace(
            price=float(product.myntra_price),
            merchant="Myntra", source="myntra",
            source_icon="fas fa-shirt",
            delivery_time_hours=36,
            external_url=product.myntra_url or _retailer_search_url("myntra", pname),
        ))
    return min(sources, key=lambda s: s.price) if sources else None


def _local_offer_payload(product):
    """Return the cheapest active local merchant offer for a product."""
    offer = product.offers.filter(is_active=True).select_related("merchant").order_by("price").first()
    if not offer:
        return None
    return SimpleNamespace(
        price=float(offer.price),
        original_price=float(offer.original_price) if offer.original_price else None,
        merchant=offer.merchant.shop_name,
        merchant_id=offer.merchant_id,
        delivery_time_hours=offer.delivery_time_hours,
        source="local",
        source_icon="fas fa-store",
        verified=offer.merchant.verified,
        discount_percentage=_discount_percentage(offer.price, offer.original_price),
        external_url=None,
    )


def _product_card(product):
    rating = None
    if product.amazon_rating is not None:
        rating = float(product.amazon_rating)
    elif product.flipkart_rating is not None:
        rating = float(product.flipkart_rating)
    elif product.myntra_rating is not None:
        rating = float(product.myntra_rating)

    best_online = _online_offer_payload(product)
    best_local = _local_offer_payload(product)
    best_offer = _best_offer_payload(product)
    category_name = _pretty_category_label(product.category.name if product.category else "General")

    # Savings: difference between local and cheapest online (if both exist)
    savings = None
    if best_local and best_online:
        diff = round(best_local.price - best_online.price, 2)
        if diff > 0:
            savings = SimpleNamespace(amount=diff, cheaper="online")
        elif diff < 0:
            savings = SimpleNamespace(amount=abs(diff), cheaper="local")

    return SimpleNamespace(
        id=product.id,
        name=product.name,
        image_url=product.image_url,
        category=SimpleNamespace(name=category_name),
        category_id=product.category_id,
        brand_name=product.brand.name if product.brand else None,
        best_offer=best_offer,
        best_online=best_online,
        best_local=best_local,
        savings=savings,
        rating=rating,
        reviews_count="",
        description=product.description or "",
    )


def _default_redirect_for_user(user):
    if getattr(user, "is_staff", False):
        return "admin_dashboard"
    if getattr(user, "is_merchant", False):
        return "merchant_dashboard"
    return "user_dashboard"


def _pretty_category_label(value):
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("&", " & ")
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _is_customer_user(user):
    return bool(user and user.is_authenticated and not user.is_staff and not user.is_merchant)


def _online_baseline_source(product):
    prices = []
    if product.amazon_price is not None:
        prices.append(("Amazon", float(product.amazon_price)))
    if product.flipkart_price is not None:
        prices.append(("Flipkart", float(product.flipkart_price)))
    if product.myntra_price is not None:
        prices.append(("Myntra", float(product.myntra_price)))
    if not prices:
        return None
    return min(prices, key=lambda item: item[1])[0]


def _category_spotlights(cards, categories):
    cards_by_category = defaultdict(list)
    for card in cards:
        if card.category_id:
            cards_by_category[card.category_id].append(card)

    spotlights = []
    for category in categories:
        category_cards = cards_by_category.get(category.id, [])
        if not category_cards:
            continue
        category_cards.sort(key=lambda item: (item.best_offer.price, item.name.lower()))
        spotlights.append(
            SimpleNamespace(
                id=category.id,
                name=category.name,
                product_count=category.product_count,
                product=category_cards[0],
            )
        )
    return spotlights


def _is_homepage_showcase_card(card):
    text = " ".join(
        [
            card.name or "",
            card.category.name if getattr(card, "category", None) else "",
            card.brand_name or "",
            card.description or "",
        ]
    ).lower()
    excluded_keywords = (
        "charger",
        "charging cable",
        "usb cable",
        "data cable",
        "adapter",
    )
    return not any(keyword in text for keyword in excluded_keywords)


def _max_offer_discount(product):
    discounts = []
    for offer in product.offers.all():
        if not offer.is_active:
            continue
        discount = _discount_percentage(offer.price, offer.original_price)
        if discount is not None:
            discounts.append(discount)
    return max(discounts) if discounts else None


def _updated_querystring(querydict, **updates):
    params = querydict.copy()
    for key, value in updates.items():
        if value in (None, "", [], (), set()):
            params.pop(key, None)
            continue
        if isinstance(value, (list, tuple, set)):
            params.setlist(key, [str(item) for item in value])
        else:
            params[key] = str(value)
    return params.urlencode()


def _authenticate_from_email_or_username(identifier, password):
    user = User.objects.filter(email__iexact=(identifier or "").strip()).first()
    if user:
        return authenticate(username=user.username, password=password)
    return authenticate(username=(identifier or "").strip(), password=password)


def _recent_log_lines(path: Path, limit: int = 40):
    if not path.exists() or not path.is_file():
        return []

    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []

    return lines[-limit:]


def _dataset_directory_entries():
    dataset_dir = Path(settings.BASE_DIR) / "dataset"
    tracked_paths = {
        name: Path(path).resolve()
        for name, path in ((getattr(settings, "AI_SETTINGS", {}) or {}).get("DATASET_PATHS", {}) or {}).items()
    }
    entries = []
    if not dataset_dir.exists():
        return entries

    for item in sorted(dataset_dir.iterdir(), key=lambda path: (not path.is_file(), path.name.lower())):
        try:
            stat = item.stat()
        except OSError:
            continue

        tracked_as = [key for key, tracked_path in tracked_paths.items() if tracked_path == item.resolve()]
        entries.append(
            SimpleNamespace(
                name=item.name,
                path=str(item),
                is_file=item.is_file(),
                size_mb=round((stat.st_size or 0) / (1024 * 1024), 2),
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.get_current_timezone()),
                tracked_as=tracked_as,
            )
        )

    return entries


class BaseSiteView(TemplateView):
    """Shared context for frontend pages."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        request_user = self.request.user

        if request_user.is_authenticated:
            cart = Cart.objects.filter(user=request_user).prefetch_related("items").first()
            cart_items_count = sum(item.quantity for item in cart.items.all()) if cart else 0
            unread_notifications_count = request_user.notifications.filter(is_read=False).count()
        else:
            cart_items_count = 0
            unread_notifications_count = 0

        context.setdefault("cart_items_count", cart_items_count)
        context.setdefault("unread_notifications_count", unread_notifications_count)
        return context


class FrontendLoginRequiredMixin(LoginRequiredMixin):
    login_url = reverse_lazy("login")
    redirect_field_name = "next"


class MerchantRequiredMixin(FrontendLoginRequiredMixin, UserPassesTestMixin):
    denied_message = "Merchant access is required for that page."

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_merchant and hasattr(
            self.request.user, "merchant_profile"
        )

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, self.denied_message)
        return redirect("index")


class CustomerRequiredMixin(FrontendLoginRequiredMixin, UserPassesTestMixin):
    denied_message = "Customer access is required for that page."

    def test_func(self):
        return self.request.user.is_authenticated and not self.request.user.is_staff and not self.request.user.is_merchant

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, self.denied_message)
        return redirect("index")


class StaffRequiredMixin(FrontendLoginRequiredMixin, UserPassesTestMixin):
    denied_message = "Admin access is required for that page."
    login_url = reverse_lazy("admin_login")

    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return super().handle_no_permission()
        messages.error(self.request, self.denied_message)
        return redirect("index")


class DashboardShellContextMixin:
    dashboard_section = "overview"
    dashboard_title = "User Dashboard"
    dashboard_intro = "Use the sidebar to move across search, basket, notifications, and profile pages."

    def _dashboard_shell_enabled(self):
        return _is_customer_user(self.request.user) or self.request.path.startswith("/dashboard/")

    def get_dashboard_title(self):
        return self.dashboard_title

    def get_dashboard_intro(self):
        return self.dashboard_intro

    def get_dashboard_navigation(self):
        items = [
            ("overview", "user_dashboard", "fa-gauge-high", "Dashboard"),
            ("results", "dashboard_results", "fa-magnifying-glass", "Search Results"),
            ("barcode", "dashboard_barcode", "fa-barcode", "Barcode"),
            ("visual", "dashboard_visual_search", "fa-camera", "Visual Search"),
            ("basket", "dashboard_basket", "fa-basket-shopping", "Smart Basket"),
            ("checkout", "dashboard_checkout", "fa-credit-card", "Checkout"),
            ("orders", "dashboard_orders", "fa-receipt", "Orders"),
            ("deal_lock", "dashboard_deal_lock", "fa-ticket", "Deal-Lock"),
            ("notifications", "dashboard_notifications", "fa-bell", "Notifications"),
            ("profile", "dashboard_profile", "fa-user-gear", "Profile"),
        ]
        return [
            SimpleNamespace(
                key=key,
                url=reverse(route_name),
                icon=icon,
                label=label,
                active=(key == self.dashboard_section),
            )
            for key, route_name, icon, label in items
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dashboard_mode = self._dashboard_shell_enabled()
        route_prefix = "dashboard_" if dashboard_mode else ""
        context.update(
            {
                "dashboard_mode": dashboard_mode,
                "dashboard_section": self.dashboard_section,
                "dashboard_title": self.get_dashboard_title(),
                "dashboard_intro": self.get_dashboard_intro(),
                "search_route_name": f"{route_prefix}results" if dashboard_mode else "product_search",
                "product_detail_route_name": "dashboard_product_detail" if dashboard_mode else "product_detail",
                "notifications_route_name": "dashboard_notifications" if dashboard_mode else "notifications",
                "profile_route_name": "dashboard_profile" if dashboard_mode else "profile",
                "basket_route_name": "dashboard_basket" if dashboard_mode else "cart",
                "deal_lock_route_name": "dashboard_deal_lock",
            }
        )
        if dashboard_mode:
            context["dashboard_nav"] = self.get_dashboard_navigation()
            context["dashboard_user_location"] = (
                f"{self.request.user.location_lat}, {self.request.user.location_lng}"
                if _is_customer_user(self.request.user)
                and self.request.user.location_lat is not None
                and self.request.user.location_lng is not None
                else "Location not set"
            )
        return context


class HomePageView(BaseSiteView):
    template_name = "index.html"
    HOMEPAGE_SAMPLE_LIMIT = 72

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        products = SearchService.get_trending_products(limit=self.HOMEPAGE_SAMPLE_LIMIT)
        product_cards = [_product_card(product) for product in products]
        live_cards = [card for card in product_cards if card.best_offer]
        # Prioritize products with images, then sort by price
        live_cards.sort(key=lambda item: (not bool(item.image_url), item.best_offer.price, item.name.lower()))
        showcase_cards = [card for card in live_cards if _is_homepage_showcase_card(card)] or live_cards

        categories = list(
            Category.objects.annotate(product_count=Count("products"))
            .filter(product_count__gt=0)
            .order_by("-product_count", "name")[:8]
        )

        verified_offers = list(
            Offer.objects.filter(is_active=True, merchant__verified=True)
            .select_related("product", "merchant", "product__category", "product__brand")
            .order_by("price")[:8]
        )

        verified_deals = []
        for offer in verified_offers:
            verified_deals.append(
                SimpleNamespace(
                    product=_product_card(offer.product),
                    merchant_name=offer.merchant.shop_name,
                    offer_price=float(offer.price),
                    original_price=float(offer.original_price) if offer.original_price else None,
                    discount_percentage=_discount_percentage(offer.price, offer.original_price),
                )
            )

        hot_deal_buckets = []
        price_ranges = [
            (None, 99, "Rs.0 - 99"),
            (100, 199, "Rs.100 - 199"),
            (200, 299, "Rs.200 - 299"),
            (300, 399, "Rs.300 - 399"),
            (400, 499, "Rs.400 - 499"),
            (500, 999, "Rs.500 - 999"),
        ]
        _results_url = reverse('dashboard_results') if self.request.user.is_authenticated else reverse('product_search')
        for min_price, max_price, display in price_ranges:
            hot_deal_buckets.append(
                SimpleNamespace(
                    threshold=max_price,
                    display=display,
                    label=f"Deals in {display}",
                    count=sum(
                        1
                        for card in live_cards
                        if (min_price is None or card.best_offer.price >= min_price) and card.best_offer.price <= max_price
                    ),
                    href=(
                        f"{_results_url}?max_price={max_price}&sort_by=price_low"
                        if min_price is None
                        else f"{_results_url}?min_price={min_price}&max_price={max_price}&sort_by=price_low"
                    ),
                )
            )

        discounted_offers = [
            offer
            for offer in Offer.objects.filter(is_active=True, original_price__gt=F("price")).select_related(
                "product", "merchant"
            )
        ]
        discount_buckets = []
        for threshold in [10, 20, 30, 40]:
            count = 0
            for offer in discounted_offers:
                discount = _discount_percentage(offer.price, offer.original_price)
                if discount is not None and discount >= threshold:
                    count += 1
            discount_buckets.append(
                SimpleNamespace(
                    threshold=threshold,
                    label=f"{threshold}%+ Off",
                    count=count,
                    href=f"{_results_url}?sort_by=price_low&min_discount={threshold}",
                )
            )

        hero_metrics = [
            SimpleNamespace(label="Catalog Products", value=Product.objects.count()),
            SimpleNamespace(label="Live Local Offers", value=Offer.objects.filter(is_active=True).count()),
            SimpleNamespace(label="Verified Merchants", value=Merchant.objects.filter(verified=True).count()),
            SimpleNamespace(label="Tracked Categories", value=Category.objects.count()),
        ]

        supported_sources = ["Amazon", "Flipkart"]
        if Product.objects.filter(Q(myntra_price__isnull=False) | Q(myntra_url__isnull=False)).exists():
            supported_sources.append("Myntra")
        supported_sources.extend(
            list(Merchant.objects.filter(verified=True).order_by("shop_name").values_list("shop_name", flat=True)[:10])
        )

        context.update(
            {
                "hero_metrics": hero_metrics,
                "hero_search_examples": [card.name for card in showcase_cards[:5]],
                "catalog_preview": showcase_cards[:12] if showcase_cards else product_cards[:12],
                "featured_deals": showcase_cards[:8],
                "verified_deals": verified_deals,
                "hot_deal_buckets": hot_deal_buckets,
                "discount_buckets": discount_buckets,
                "category_spotlights": _category_spotlights(showcase_cards, categories),
                "supported_sources": supported_sources,

                "why_cards": [
                    SimpleNamespace(
                        title="Hybrid Comparison",
                        copy="Ranks Amazon, Flipkart, and verified local merchant offers in one search result.",
                    ),
                    SimpleNamespace(
                        title="ML Ranking Engine",
                        copy="Uses weighted scoring for price, delivery speed, rating, and merchant trust.",
                    ),
                    SimpleNamespace(
                        title="Smart Basket Logic",
                        copy="Builds a split-purchase strategy instead of forcing a single-source checkout.",
                    ),
                    SimpleNamespace(
                        title="Real Dataset Backing",
                        copy="Catalog data is loaded from the dataset folder instead of placeholder frontend content.",
                    ),
                ],
            }
        )
        return context


class FeatureStatusPageView(BaseSiteView):
    template_name = "feature_status.html"


class SearchResultsPageView(DashboardShellContextMixin, BaseSiteView):
    template_name = "users/search_results.html"
    dashboard_section = "results"
    dashboard_title = "Search Results"
    dashboard_intro = "Search the catalog, compare online and local offers, and review ranked results."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        sort_by = self.request.GET.get("sort_by", "relevance")
        fallback_message = None
        selected_categories = {item.strip() for item in self.request.GET.getlist("category") if item.strip()}

        filters = {
            "min_price": self.request.GET.get("min_price"),
            "max_price": self.request.GET.get("max_price"),
            "category": list(selected_categories),
            "verified_only": self.request.GET.get("verified_only") == "on",
            "min_discount": self.request.GET.get("min_discount"),
        }
        has_explicit_filters = bool(
            filters["min_price"]
            or filters["max_price"]
            or filters["category"]
            or filters["verified_only"]
            or filters["min_discount"]
        )

        is_trending_view = not query and not has_explicit_filters and sort_by == "relevance"

        if not is_trending_view:
            products = SearchService.search_products(
                query=query,
                min_price=filters["min_price"],
                max_price=filters["max_price"],
                sort_by=sort_by,
            )
        else:
            products = SearchService.get_trending_products(limit=24)

        if not products and query:
            fallback_message = (
                f'No real dataset match was found for "{query}". '
                "Try another keyword or relax the selected filters."
            )

        # For the default trending view, also pull external fashion feed items
        external_fashion_cards = []
        if is_trending_view and getattr(settings, "ENABLE_EXTERNAL_TRENDING_FEEDS", False):
            try:
                from apps.api.external_feeds import ExternalFashionFeedService
                feed = ExternalFashionFeedService.get_female_footwear(limit=12)
                if feed.get("status") == "ok":
                    for item in feed.get("items", []):
                        if not item.get("price_value"):
                            continue
                        ext_url = f"https://www.myntra.com/{item.get('tag', '').replace(' ', '-')}" if item.get("tag") else "https://www.myntra.com"
                        external_fashion_cards.append(SimpleNamespace(
                            id=None,
                            name=item.get("description") or item.get("brand") or "Fashion Item",
                            image_url=item.get("image_url"),
                            category=SimpleNamespace(name=item.get("tag") or "Fashion"),
                            category_id=None,
                            brand_name=item.get("brand"),
                            rating=None,
                            reviews_count="",
                            description="",
                            is_external=True,
                            best_offer=SimpleNamespace(
                                price=item["price_value"],
                                original_price=None,
                                merchant="Myntra",
                                merchant_id=None,
                                delivery_time_hours=36,
                                source="myntra",
                                source_icon="fas fa-shirt",
                                verified=True,
                                discount_percentage=None,
                                external_url=ext_url,
                            ),
                        ))
            except Exception:
                pass

        if selected_categories:
            products = [
                product for product in products if product.category and product.category.name in selected_categories
            ]

        if filters["verified_only"]:
            products = [
                product
                for product in products
                if product.offers.filter(is_active=True, merchant__verified=True).exists()
            ]

        if filters["min_discount"] not in (None, ""):
            try:
                min_discount = float(filters["min_discount"])
            except (TypeError, ValueError):
                min_discount = None
            if min_discount is not None:
                products = [
                    product
                    for product in products
                    if (_max_offer_discount(product) or 0) >= min_discount
                ]

        product_cards = [_product_card(product) for product in products]

        # Merge external fashion feed cards into the first page for trending view
        if is_trending_view and external_fashion_cards:
            # Interleave external cards throughout the list for variety
            merged = []
            ext_iter = iter(external_fashion_cards)
            for i, card in enumerate(product_cards):
                merged.append(card)
                if (i + 1) % 4 == 0:
                    ext_card = next(ext_iter, None)
                    if ext_card:
                        merged.append(ext_card)
            merged.extend(ext_iter)  # append any remaining external cards
            product_cards = merged

        page = self.request.GET.get("page", 1)
        paginator = Paginator(product_cards, 12)

        try:
            page_obj = paginator.page(page)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)

        hidden_filter_categories = {"musicalinstruments", "car&motorbike"}
        category_filters = list(
            Category.objects.annotate(product_count=Count("products"))
            .filter(product_count__gt=0)
            .order_by("-product_count", "name")
            .values("name", "product_count")
        )
        category_filters = [
            {
                **category,
                "display_name": _pretty_category_label(category.get("name")),
            }
            for category in category_filters
            if str(category.get("name", "")).strip().lower() not in hidden_filter_categories
        ]

        filter_meta = {
            "categories": category_filters,
            "brands": [],
        }

        context.update(
            {
                "query": query,
                "products": page_obj.object_list,
                "categories": filter_meta["categories"],
                "brands": filter_meta["brands"],
                "page_obj": page_obj,
                "total_count": len(product_cards),
                "fallback_message": fallback_message,
                "selected_categories": selected_categories,
                "verified_only": filters["verified_only"],
                "is_trending_view": is_trending_view,
                "selected_min_discount": filters["min_discount"],
                "sort_by": sort_by,
                "sort_querystrings": {
                    option: _updated_querystring(self.request.GET, sort_by=option, page=None)
                    for option in ["relevance", "price_low", "price_high", "rating"]
                },
                "pagination_querystring": _updated_querystring(self.request.GET, page=None),
            }
        )
        return context


class ProductDetailPageView(DashboardShellContextMixin, BaseSiteView):
    template_name = "users/product_detail.html"
    dashboard_section = "results"
    dashboard_title = "Product Detail"
    dashboard_intro = "Inspect the best available offers before adding products to your basket or requesting a price match."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product_id = kwargs.get("product_id")
        details = ProductService.get_product_details(
            product_id, self.request.user if self.request.user.is_authenticated else None
        )
        if not details:
            raise Http404("Product not found")

        product = details["product"]

        offers = [
            SimpleNamespace(
                id=offer.id,
                price=offer.price,
                delivery_time_hours=offer.delivery_time_hours,
                merchant=SimpleNamespace(
                    id=offer.merchant.id,
                    shop_name=offer.merchant.shop_name,
                    address=offer.merchant.address or "Location unavailable",
                ),
            )
            for offer in details["offers"]
        ]

        comparison_options = []
        for candidate in ProductService.get_comparison_candidates(product_id):
            match_type = candidate.get("match_type", "exact")
            match_score = candidate.get("match_score")
            comparison_options.append(
                SimpleNamespace(
                    product_id=candidate.get("product_id", product.id),
                    product_name=candidate.get("product_name", product.name),
                    source=candidate["source"],
                    source_name=candidate["source_name"],
                    merchant_id=candidate["merchant_id"],
                    price=float(candidate["price"]),
                    original_price=float(candidate["original_price"]) if candidate.get("original_price") is not None else None,
                    delivery_time_hours=candidate["delivery_time_hours"],
                    external_url=candidate["external_url"],
                    verified=candidate["verified"],
                    rating=candidate["rating"],
                    address=candidate["merchant"].address if candidate["merchant"] else None,
                    match_type=match_type,
                    match_score=match_score,
                    match_label="Exact product match" if match_type == "exact" else ("Search redirect" if match_type == "search_redirect" else "Related catalog match"),
                    match_note=(
                        "This price is attached to the same product row you opened."
                        if match_type == "exact"
                        else (
                            f"No price in catalog — click to search on {candidate.get('source_name', 'this platform')}."
                            if match_type == "search_redirect"
                            else f"Matched from a related catalog row: {candidate.get('product_name', product.name)}"
                        )
                    ),
                    is_price_estimated=bool(candidate.get("is_price_estimated", False)),
                )
            )

        available_prices = [option.price for option in comparison_options]
        lowest_price = min(available_prices) if available_prices else None
        highest_price = max(available_prices) if available_prices else None
        average_price = round(sum(available_prices) / len(available_prices), 2) if available_prices else None
        current_best = comparison_options[0] if comparison_options else None

        if lowest_price is not None and highest_price is not None and highest_price > 0:
            savings_percent = round(((highest_price - lowest_price) / highest_price) * 100, 2)
        else:
            savings_percent = 0.0

        if comparison_options:
            deal_score = min(100, round(56 + (savings_percent * 1.15) + (len(comparison_options) * 6)))
            if lowest_price is not None and average_price is not None:
                if lowest_price < average_price:
                    insight_title = "Lower Than Average Price"
                    insight_copy = "The current best option is below the average comparable price in the loaded catalog."
                elif lowest_price == average_price:
                    insight_title = "At the Current Average"
                    insight_copy = "The current best option is aligned with the average comparable price."
                else:
                    insight_title = "Above Average Price"
                    insight_copy = "The current best option is above the average comparable price for this match set."
            else:
                insight_title = "Single Price Source"
                insight_copy = "Only one comparable price source is currently available for this product."
        else:
            deal_score = 0
            insight_title = "No Active Comparison"
            insight_copy = "No active comparable sources are available for this product yet."

        source_slots = []
        for source_key, source_label in [
            ("amazon", "Amazon"),
            ("flipkart", "Flipkart"),
            ("myntra", "Myntra"),
            ("local", "Local Shops"),
        ]:
            source_options = [option for option in comparison_options if option.source == source_key]
            best_source_option = source_options[0] if source_options else None
            if best_source_option:
                if best_source_option.match_type == "catalog_match":
                    note = f"Matched from related catalog row: {best_source_option.product_name}"
                elif source_key == "local":
                    note = "Exact local merchant listing available"
                else:
                    note = "Exact marketplace row available"
            else:
                if source_key == "local":
                    note = "No active local merchant offer is attached to this product."
                else:
                    note = f"No comparable {source_label} row is currently attached or matched in the loaded catalog."

            relative_delta_percent = None
            if best_source_option and lowest_price and best_source_option.price > lowest_price:
                relative_delta_percent = round(((best_source_option.price - lowest_price) / lowest_price) * 100, 2)

            source_slots.append(
                SimpleNamespace(
                    key=source_key,
                    label=source_label,
                    available=bool(best_source_option),
                    count=len(source_options),
                    option=best_source_option,
                    note=note,
                    is_best=bool(best_source_option and lowest_price is not None and best_source_option.price == lowest_price),
                    relative_delta_percent=relative_delta_percent,
                )
            )

        available_source_slots = [slot for slot in source_slots if slot.available]
        missing_source_labels = [slot.label for slot in source_slots if not slot.available]

        enable_live_product_page_enrichment = bool(getattr(settings, "ENABLE_LIVE_PRODUCT_PAGE_ENRICHMENT", False))

        amazon_review_summary = None
        amazon_product_snapshot = None
        amazon_slot = next((slot for slot in source_slots if slot.key == "amazon" and slot.available and slot.option), None)
        if enable_live_product_page_enrichment and amazon_slot:
            amazon_review_summary = SimpleNamespace(**RealAIService.get_amazon_reviews(amazon_slot.option.product_id, limit=4))
            amazon_product_snapshot_data = RealAIService.get_amazon_product_snapshot(amazon_slot.option.product_id)
            if amazon_product_snapshot_data.get("status") == "ok":
                amazon_product_snapshot = SimpleNamespace(**amazon_product_snapshot_data)

        live_retail_prices = RealTimePriceService.fetch_live_prices(product) if enable_live_product_page_enrichment else []

        context["product"] = SimpleNamespace(
            id=product.id,
            name=product.name,
            category=SimpleNamespace(name=product.category.name if product.category else "General"),
            offers=offers,
            image_url=product.image_url,
            amazon_price=product.amazon_price,
            flipkart_price=product.flipkart_price,
            myntra_price=product.myntra_price,
            rating=float(product.amazon_rating)
            if product.amazon_rating is not None
            else (
                float(product.flipkart_rating)
                if product.flipkart_rating is not None
                else (float(product.myntra_rating) if product.myntra_rating is not None else None)
            ),
            description=product.description or "Real catalog product sourced from the configured datasets.",
            reviews_count="",
        )
        context["comparison_options"] = comparison_options
        context["comparison_summary"] = SimpleNamespace(
            available_count=len(comparison_options),
            lowest_price=lowest_price,
            highest_price=highest_price,
            average_price=average_price,
            savings_percent=savings_percent,
            deal_score=deal_score,
            insight_title=insight_title,
            insight_copy=insight_copy,
            current_best=current_best,
        )
        context["source_slots"] = source_slots
        context["available_source_slots"] = available_source_slots
        context["missing_source_labels"] = missing_source_labels
        context["amazon_reviews"] = amazon_review_summary
        context["amazon_product_snapshot"] = amazon_product_snapshot
        context["live_retail_prices"] = live_retail_prices
        context["enable_live_product_page_enrichment"] = enable_live_product_page_enrichment
        return context


class CartPageView(CustomerRequiredMixin, DashboardShellContextMixin, BaseSiteView):
    template_name = "users/cart.html"
    dashboard_section = "basket"
    dashboard_title = "Tracked Cart"
    dashboard_intro = "Review the products you have added and the current best source for each one."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart, cart_items, subtotal, total_items = CartOrderService.cart_items_with_totals(self.request.user)

        items = []
        for item in cart_items:
            unit_price = float(item.unit_price_snapshot or 0)
            total_price = round(unit_price * item.quantity, 2)
            items.append(
                SimpleNamespace(
                    id=item.id,
                    quantity=item.quantity,
                    total_price=total_price,
                    unit_price=unit_price,
                    source=item.selected_source,
                    source_name=item.selected_source_name,
                    delivery_time_hours=item.delivery_time_hours,
                    external_url=(
                        item.product.amazon_url if item.selected_source == "amazon"
                        else item.product.flipkart_url if item.selected_source == "flipkart"
                        else item.product.myntra_url if item.selected_source == "myntra"
                        else None
                    ),
                    merchant=SimpleNamespace(
                        id=item.merchant_id,
                        shop_name=item.merchant.shop_name if item.merchant else item.selected_source_name,
                    ),
                    product=SimpleNamespace(
                        id=item.product.id,
                        name=item.product.name,
                        image_url=item.product.image_url,
                        category=SimpleNamespace(name=item.product.category.name if item.product.category else "General"),
                        amazon_price=item.product.amazon_price,
                    ),
                )
            )

        context.update(
            {
                "cart_item_records": cart_items,
                "items": items,
                "total_items": total_items,
                "subtotal": round(float(subtotal), 2),
                "total": round(float(subtotal), 2),
                "has_external_items": any(item.source in {"amazon", "flipkart", "myntra"} for item in items),
                "has_local_items": any(item.source == "local" for item in items),
            }
        )
        return context


class UserDashboardPageView(CustomerRequiredMixin, DashboardShellContextMixin, BaseSiteView):
    template_name = "users/dashboard.html"
    dashboard_section = "overview"
    dashboard_title = "Dashboard"
    dashboard_intro = "Search products, capture your location, review alerts, and continue the comparison workflow."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart, _ = Cart.objects.get_or_create(user=self.request.user)
        recent_activities = list(
            self.request.user.activities.select_related("product", "merchant").order_by("-created_at")[:8]
        )
        recent_searches = []
        for activity in self.request.user.activities.filter(activity_type="search").order_by("-created_at")[:6]:
            query = (activity.metadata or {}).get("query") or (activity.metadata or {}).get("category")
            if not query:
                continue
            recent_searches.append(
                SimpleNamespace(
                    label=query,
                    created_at=activity.created_at,
                    url=f"{reverse('dashboard_results')}?q={query}",
                )
            )
        recommendations = UserService.get_recommendations(self.request.user, limit=6)
        pending_requests = self.request.user.price_match_requests.filter(status="pending").count()
        unread_price_drops = self.request.user.notifications.filter(
            is_read=False, notification_type="price_drop"
        ).count()
        active_alerts = list(self.request.user.notifications.order_by("-created_at")[:4])
        quick_categories = list(
            Category.objects.annotate(product_count=Count("products"))
            .filter(product_count__gt=0)
            .order_by("-product_count", "name")[:6]
        )

        current_savings = 0.0
        for item in cart.items.select_related("product").prefetch_related("product__offers__merchant"):
            best_offer = _best_offer_payload(item.product)
            online_baseline = _online_baseline_price(item.product)
            if best_offer and online_baseline is not None and best_offer.price < online_baseline:
                current_savings += (online_baseline - best_offer.price) * item.quantity

        recommendations_cards = [_product_card(product) for product in recommendations]
        insight_message = None
        if recommendations_cards:
            best_pick = recommendations_cards[0]
            if best_pick.best_offer:
                insight_message = (
                    f"Best next recommendation: {best_pick.name} from {best_pick.best_offer.merchant} "
                    f"at Rs.{best_pick.best_offer.price:.2f}."
                )

        context.update(
            {
                "stats": {
                    "total_saved": round(current_savings, 2),
                    "active_requests": pending_requests,
                    "price_drops_alerts": unread_price_drops,
                },
                "recent_activities": recent_activities,
                "recent_searches": recent_searches,
                "active_alerts": active_alerts,
                "quick_categories": quick_categories,
                "recommendations": recommendations_cards,
                "insight_message": insight_message,
            }
        )
        return context


class NotificationsPageView(CustomerRequiredMixin, DashboardShellContextMixin, BaseSiteView):
    template_name = "users/notifications.html"
    dashboard_section = "notifications"
    dashboard_title = "Notifications"
    dashboard_intro = "Track price-drop alerts, offer updates, and confirmation messages."

    def post(self, request, *args, **kwargs):
        if request.POST.get("mark_all") == "1":
            updated_count = request.user.notifications.filter(is_read=False).update(is_read=True)
            messages.success(request, f"Marked {updated_count} notification(s) as read.")
        if request.path.startswith("/dashboard/"):
            return redirect("dashboard_notifications")
        return redirect("notifications")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["notifications"] = list(self.request.user.notifications.order_by("-created_at")[:50])
        return context


class DashboardSearchResultsPageView(CustomerRequiredMixin, SearchResultsPageView):
    dashboard_section = "results"
    dashboard_title = "Search Results"
    dashboard_intro = "Review ranked offers, refine filters, and move into product detail or deal-lock pages."


class DashboardProductDetailPageView(CustomerRequiredMixin, ProductDetailPageView):
    dashboard_section = "results"
    dashboard_title = "Product Detail"
    dashboard_intro = "Compare product pricing in detail and continue into basket or deal-lock flows."


class BasketPageView(CartPageView):
    template_name = "users/smart_basket.html"
    dashboard_section = "basket"
    dashboard_title = "Smart Basket"
    dashboard_intro = "Optimize the products in your tracked cart using the current catalog prices."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart_item_records = context.get("cart_item_records") or []
        if cart_item_records:
            optimization = RealAIService.optimize_cart_items(cart_item_records)
        else:
            optimization = None

        grouped_items = []
        if optimization and optimization.get("best_option"):
            for merchant_name, items in optimization["best_option"].get("products_by_store", {}).items():
                grouped_items.append(
                    SimpleNamespace(
                        merchant=merchant_name,
                        items=items,
                        total=round(sum(entry["line_total"] for entry in items), 2),
                    )
                )

        optimized_total = round(
            float(optimization["best_option"]["total_cost"]),
            2,
        ) if optimization and optimization.get("best_option") else round(float(context.get("total", 0)), 2)
        current_total = round(float(context.get("total", 0)), 2)
        current_cart_savings = round(max(current_total - optimized_total, 0), 2)
        basket_checkout_blocked = bool(context.get("has_external_items") and context.get("has_local_items"))

        context.update(
            {
                "optimization": optimization,
                "optimized_groups": grouped_items,
                "optimized_total": optimized_total,
                "current_cart_savings": current_cart_savings,
                "basket_checkout_blocked": basket_checkout_blocked,
            }
        )
        return context


class DashboardCartAddView(CustomerRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        next_url = request.POST.get("next") or reverse("dashboard_basket")
        product_id = request.POST.get("product_id")
        quantity = request.POST.get("quantity", 1)
        source = request.POST.get("source")
        merchant_id = request.POST.get("merchant_id") or None

        try:
            cart_item, candidate = CartOrderService.add_to_cart(
                request.user,
                product_id=product_id,
                quantity=quantity,
                source=source,
                merchant_id=merchant_id,
            )
            messages.success(
                request,
                f"{cart_item.product.name} added to cart from {candidate['source_name']} at Rs.{float(candidate['price']):.2f}.",
            )
        except (ValidationError, ValueError) as exc:
            messages.error(request, str(exc))
        except Product.DoesNotExist:
            messages.error(request, "Product not found.")

        return redirect(next_url)


class DashboardCartUpdateView(CustomerRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        product_id = kwargs.get("product_id")
        quantity = request.POST.get("quantity", 1)
        try:
            result = CartOrderService.update_cart_item(request.user, product_id, quantity)
            if result is None:
                messages.success(request, "Item removed from cart.")
            else:
                messages.success(request, "Cart quantity updated.")
        except (Cart.DoesNotExist, CartItem.DoesNotExist):
            messages.error(request, "Cart item not found.")
        except (ValidationError, ValueError) as exc:
            messages.error(request, str(exc))
        return redirect("dashboard_basket")


class DashboardCartRemoveView(CustomerRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        product_id = kwargs.get("product_id")
        try:
            cart = Cart.objects.get(user=request.user)
            cart_item = CartItem.objects.get(cart=cart, product_id=product_id)
            product_name = cart_item.product.name
            cart_item.delete()
            UserActivity.objects.create(
                user=request.user,
                activity_type="remove_from_cart",
                product_id=product_id,
            )
            messages.success(request, f"{product_name} removed from cart.")
        except (Cart.DoesNotExist, CartItem.DoesNotExist):
            messages.error(request, "Cart item not found.")
        return redirect("dashboard_basket")


class CheckoutPageView(CustomerRequiredMixin, DashboardShellContextMixin, BaseSiteView):
    template_name = "users/checkout.html"
    dashboard_section = "checkout"
    dashboard_title = "Checkout"
    dashboard_intro = "Review your selected sources, choose the valid payment route, and create the order."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        _, cart_items, total, total_items = CartOrderService.cart_items_with_totals(self.request.user)
        items = [
            SimpleNamespace(
                product_name=item.product.name,
                quantity=item.quantity,
                source=item.selected_source,
                source_name=item.selected_source_name,
                unit_price=float(item.unit_price_snapshot or 0),
                line_total=float((item.unit_price_snapshot or 0) * item.quantity),
            )
            for item in cart_items
        ]
        has_external_items = any(item.source in {"amazon", "flipkart", "myntra"} for item in items)
        has_local_items = any(item.source == "local" for item in items)
        context.update(
            {
                "checkout_items": items,
                "checkout_total": float(total),
                "checkout_total_items": total_items,
                "has_external_items": has_external_items,
                "has_local_items": has_local_items,
                "payment_choices": [SimpleNamespace(**item) for item in CartOrderService.payment_choices(has_local_items, has_external_items)],
                "payment_config": CartOrderService.payment_configuration(),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        try:
            order, external_links = CartOrderService.create_order_from_cart(
                request.user,
                delivery_address=request.POST.get("delivery_address", "").strip(),
                payment_method=request.POST.get("payment_method", "").strip(),
            )
            messages.success(request, f"Order {order.id} created successfully.")
            context = self.get_context_data()
            context.update(
                {
                    "created_order": order,
                    "external_checkout_links": external_links,
                    "checkout_items": [],
                    "checkout_total": 0,
                    "checkout_total_items": 0,
                    "payment_choices": [],
                }
            )
            return self.render_to_response(context)
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
            return self.render_to_response(self.get_context_data())


class OrderHistoryPageView(CustomerRequiredMixin, DashboardShellContextMixin, BaseSiteView):
    template_name = "users/orders.html"
    dashboard_section = "orders"
    dashboard_title = "Orders"
    dashboard_intro = "Review placed orders and any required external checkout links for online-source items."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        orders = list(
            Order.objects.filter(user=self.request.user)
            .prefetch_related("items", "items__product", "items__merchant")
            .order_by("-created_at")[:25]
        )
        for index, order in enumerate(orders, start=1):
            order.delivery_map = _build_order_delivery_map(order, self.request.user, index)
        context["orders"] = orders
        return context


class DashboardFeatureStatusPageView(CustomerRequiredMixin, DashboardShellContextMixin, BaseSiteView):
    template_name = "users/dashboard_status.html"
    status_icon = "fa-circle-info"
    status_title = "Feature Status"
    status_copy = "This workflow entry exists in the dashboard, but the dedicated UI is not fully wired yet."
    status_points = []
    status_cta_label = "Back to dashboard"
    status_cta_url_name = "user_dashboard"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "status_icon": self.status_icon,
                "status_title": self.status_title,
                "status_copy": self.status_copy,
                "status_points": self.status_points,
                "status_cta_label": self.status_cta_label,
                "status_cta_url": reverse(self.status_cta_url_name),
            }
        )
        return context


class BarcodeScannerPageView(CustomerRequiredMixin, DashboardShellContextMixin, BaseSiteView):
    template_name = "users/barcode.html"
    dashboard_section = "barcode"
    dashboard_title = "Barcode Scanner"
    dashboard_intro = "Lookup a product by barcode and continue into ranked results or product detail."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        barcode = self.request.GET.get("barcode", "").strip()
        scan_result = RealAIService.barcode_search(barcode) if barcode else None

        similar_matches = []
        if scan_result and scan_result.get("similar_products"):
            for product in scan_result["similar_products"]:
                detail_url = (
                    reverse("dashboard_product_detail", args=[product["id"]])
                    if product.get("id")
                    else None
                )
                similar_matches.append(
                    SimpleNamespace(
                        id=product.get("id"),
                        name=product.get("name"),
                        image_url=product.get("image_url"),
                        detail_url=detail_url,
                    )
                )

        context.update(
            {
                "barcode_query": barcode,
                "scan_result": scan_result,
                "similar_matches": similar_matches,
            }
        )
        return context


class VisualSearchPageView(CustomerRequiredMixin, DashboardShellContextMixin, BaseSiteView):
    template_name = "users/visual_search.html"
    dashboard_section = "visual"
    dashboard_title = "Visual Search"
    dashboard_intro = "Upload a product image to detect its retail category and surface real catalog matches from the loaded dataset."

    def post(self, request, *args, **kwargs):
        self.visual_search_result = None
        self.visual_search_error = None
        self.uploaded_image_name = ""

        image_file = request.FILES.get("image")
        if not image_file:
            self.visual_search_error = "Choose an image before running visual search."
            return self.render_to_response(self.get_context_data())

        self.uploaded_image_name = image_file.name
        result = RealAIService.identify_product(image_file)
        self.visual_search_result = result

        UserActivity.objects.create(
            user=request.user,
            activity_type="visual_search",
            metadata={
                "image_name": image_file.name,
                "status": result.get("status"),
                "predicted_supercategory": result.get("predicted_supercategory"),
                "predicted_category": result.get("predicted_category"),
            },
        )

        if result.get("status") in {"invalid_image", "unavailable"}:
            self.visual_search_error = result.get("message") or "The uploaded image could not be processed."

        return self.render_to_response(self.get_context_data())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        result = getattr(self, "visual_search_result", None)
        upload_error = getattr(self, "visual_search_error", None)
        uploaded_image_name = getattr(self, "uploaded_image_name", "")

        prediction_rows = []
        reference_rows = []
        matching_cards = []

        if result:
            for item in result.get("all_predictions", []) or []:
                prediction_rows.append(
                    SimpleNamespace(
                        category=item.get("predicted_category") or "Unknown",
                        supercategory=item.get("predicted_supercategory") or "Unknown",
                        confidence=float(item.get("confidence") or 0),
                        supporting_matches=int(item.get("supporting_matches") or 0),
                    )
                )

            for item in result.get("reference_matches", []) or []:
                reference_rows.append(
                    SimpleNamespace(
                        category_name=item.get("category_name") or "Unknown",
                        supercategory=item.get("supercategory") or "Unknown",
                        similarity=float(item.get("similarity") or 0),
                        reference_image=item.get("reference_image") or "",
                    )
                )

            for product in result.get("matching_products", []) or []:
                if isinstance(product, Product):
                    card = _product_card(product)
                    card.detail_url = reverse("dashboard_product_detail", args=[product.id])
                    matching_cards.append(card)

        context.update(
            {
                "visual_result": result,
                "visual_error": upload_error,
                "uploaded_image_name": uploaded_image_name,
                "prediction_rows": prediction_rows,
                "reference_rows": reference_rows,
                "matching_cards": matching_cards,
            }
        )
        return context


class DealLockPageView(CustomerRequiredMixin, DashboardShellContextMixin, BaseSiteView):
    template_name = "users/deal_lock.html"
    dashboard_section = "deal_lock"
    dashboard_title = "Deal-Lock"
    dashboard_intro = "Review price-match requests and initiate a deal-lock request for a selected product."

    def post(self, request, *args, **kwargs):
        from apps.core.models import DealLock
        product_id = kwargs.get("product_id")
        if not product_id:
            messages.error(request, "Select a product before locking a deal.")
            return redirect("dashboard_deal_lock")

        action = request.POST.get("action", "lock")
        merchant_id = request.POST.get("merchant_id")

        # --- Cancel an existing lock ---
        if action == "cancel":
            lock_id = request.POST.get("lock_id")
            try:
                lock = DealLock.objects.get(id=lock_id, user=request.user, status="active")
                lock.status = "cancelled"
                lock.save(update_fields=["status", "updated_at"])
                messages.success(request, "Deal-lock cancelled.")
            except DealLock.DoesNotExist:
                messages.error(request, "Lock not found or already cancelled.")
            return redirect("dashboard_deal_lock_product", product_id=product_id)

        # --- Create a new lock ---
        offer = (
            Offer.objects.filter(product_id=product_id, merchant_id=merchant_id, is_active=True)
            .select_related("product", "merchant")
            .first()
        )
        if not offer:
            messages.error(request, "The selected local offer could not be found.")
            return redirect("dashboard_deal_lock_product", product_id=product_id)

        # Expire any old locks for this user+offer
        DealLock.objects.filter(user=request.user, offer=offer, status="active").update(status="expired")

        lock_hours = int(request.POST.get("lock_hours", 24))
        lock_hours = max(1, min(lock_hours, 72))
        locked_until = timezone.now() + timedelta(hours=lock_hours)

        lock = DealLock.objects.create(
            user=request.user,
            offer=offer,
            locked_price=offer.price,
            lock_duration_hours=lock_hours,
            locked_until=locked_until,
            status="active",
        )

        # Also create a price-match request if local price is above online baseline
        online_baseline = _online_baseline_price(offer.product)
        if online_baseline is not None and float(offer.price) > online_baseline:
            existing_pmr = PriceMatchRequest.objects.filter(
                user=request.user, merchant=offer.merchant,
                product=offer.product, status="pending",
            ).first()
            if not existing_pmr:
                baseline_decimal = Decimal(str(online_baseline))
                PriceMatchRequest.objects.create(
                    user=request.user,
                    merchant=offer.merchant,
                    product=offer.product,
                    requested_price=baseline_decimal,
                    competitor_price=baseline_decimal,
                    competitor_source=_online_baseline_source(offer.product) or "online",
                    status="pending",
                )

        UserActivity.objects.create(
            user=request.user,
            activity_type="deal_lock_created",
            product=offer.product,
            merchant=offer.merchant,
            metadata={"lock_id": lock.id, "locked_price": float(lock.locked_price), "hours": lock_hours},
        )
        messages.success(
            request,
            f"Deal locked at Rs.{lock.locked_price} for {lock_hours} hour(s). Valid until {locked_until.strftime('%d %b %Y %I:%M %p')}."
        )
        return redirect("dashboard_deal_lock_product", product_id=product_id)

    def get_context_data(self, **kwargs):
        from apps.core.models import DealLock
        context = super().get_context_data(**kwargs)
        product_id = kwargs.get("product_id")
        product_card = None
        local_offers = []
        online_slots = []

        if product_id:
            details = ProductService.get_product_details(product_id, self.request.user)
            if not details:
                raise Http404("Product not found")

            product = details["product"]
            baseline_price = _online_baseline_price(product)
            baseline_source = _online_baseline_source(product)
            product_card = _product_card(product)
            pname = product.name or ""

            for offer in details["offers"]:
                lock = DealLock.objects.filter(
                    user=self.request.user, offer_id=offer.id,
                    status="active", locked_until__gt=timezone.now(),
                ).first()
                local_offers.append(SimpleNamespace(
                    offer_id=offer.id,
                    merchant_id=offer.merchant.id,
                    shop_name=offer.merchant.shop_name,
                    address=offer.merchant.address or "Location unavailable",
                    price=float(offer.price),
                    delivery_time_hours=offer.delivery_time_hours,
                    beats_online=(baseline_price is not None and float(offer.price) <= baseline_price),
                    savings=round(baseline_price - float(offer.price), 2) if baseline_price and float(offer.price) < baseline_price else None,
                    active_lock=lock,
                ))

            # Online comparison slots
            for src, label, delivery, url_fn in [
                ("amazon", "Amazon", "24h", lambda: product.amazon_url or f"https://www.amazon.in/s?k={pname.replace(' ', '+')}"),
                ("flipkart", "Flipkart", "48h", lambda: product.flipkart_url or f"https://www.flipkart.com/search?q={pname.replace(' ', '+')}"),
                ("myntra", "Myntra", "36h", lambda: product.myntra_url or f"https://www.myntra.com/{pname.replace(' ', '-')}"),
            ]:
                price = getattr(product, f"{src}_price", None)
                online_slots.append(SimpleNamespace(
                    source=src,
                    label=label,
                    price=float(price) if price is not None else None,
                    delivery=delivery,
                    url=url_fn(),
                    is_cheapest=False,
                ))

            # Mark cheapest online
            priced = [s for s in online_slots if s.price is not None]
            if priced:
                cheapest = min(priced, key=lambda s: s.price)
                cheapest.is_cheapest = True

            context["selected_product"] = product_card
            context["online_baseline_price"] = baseline_price
            context["online_baseline_source"] = baseline_source
            context["online_slots"] = online_slots

        # Active locks across all products for this user
        all_active_locks = list(
            DealLock.objects.filter(
                user=self.request.user, status="active",
                locked_until__gt=timezone.now(),
            ).select_related("offer__product", "offer__merchant").order_by("locked_until")[:10]
        )

        price_match_requests = list(
            self.request.user.price_match_requests.select_related("product", "merchant").order_by("-created_at")[:10]
        )

        context.update({
            "local_offers": local_offers,
            "selected_product": product_card,
            "all_active_locks": all_active_locks,
            "deal_lock_requests": price_match_requests,
            "lock_duration_choices": [
                (1, "1 hour"), (6, "6 hours"), (12, "12 hours"),
                (24, "24 hours"), (48, "48 hours"), (72, "72 hours"),
            ],
        })
        return context


class MerchantDashboardShellContextMixin:
    merchant_section = "overview"
    merchant_title = "Merchant Dashboard"
    merchant_intro = "Manage inventory, price-match requests, delivery settings, and merchant operations."

    def get_merchant_title(self):
        return self.merchant_title

    def get_merchant_intro(self):
        return self.merchant_intro

    def get_merchant_navigation(self):
        items = [
            ("overview", "merchant_dashboard", "fa-gauge-high", "Overview"),
            ("products", "merchant_inventory", "fa-boxes-stacked", "Inventory"),
            ("add_product", "merchant_add_product", "fa-plus", "Add Product"),
            ("requests", "merchant_requests", "fa-tags", "Price Requests"),
            ("deals", "merchant_deals", "fa-ticket", "Deals"),
            ("delivery", "merchant_delivery", "fa-truck-fast", "Delivery"),
            ("analytics", "merchant_analytics_dashboard", "fa-chart-line", "Analytics"),
            ("notifications", "merchant_notifications", "fa-bell", "Notifications"),
            ("profile", "merchant_profile_dashboard", "fa-user-gear", "Profile"),
            ("logout", "logout", "fa-right-from-bracket", "Logout"),
        ]
        return [
            SimpleNamespace(
                key=key,
                url=reverse(route_name),
                icon=icon,
                label=label,
                active=(key == self.merchant_section),
            )
            for key, route_name, icon, label in items
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        merchant = self.request.user.merchant_profile
        total_products = Product.objects.filter(offers__merchant=merchant).distinct().count()
        active_offers = Offer.objects.filter(merchant=merchant, is_active=True).count()
        pending_requests = PriceMatchRequest.objects.filter(merchant=merchant, status="pending").count()
        unread_notifications = self.request.user.notifications.filter(is_read=False).count()
        merchant_location = (
            f"{merchant.location_lat}, {merchant.location_lng}"
            if merchant.location_lat is not None and merchant.location_lng is not None
            else "Location not set"
        )
        context.update(
            {
                "merchant_dashboard_nav": self.get_merchant_navigation(),
                "merchant_dashboard_section": self.merchant_section,
                "merchant_dashboard_title": self.get_merchant_title(),
                "merchant_dashboard_intro": self.get_merchant_intro(),
                "merchant_shell": merchant,
                "merchant_shell_stats": {
                    "total_products": total_products,
                    "active_offers": active_offers,
                    "pending_requests": pending_requests,
                    "unread_notifications": unread_notifications,
                    "rating": float(merchant.rating or 0),
                    "location": merchant_location,
                },
            }
        )
        return context


class MerchantDashboardPageView(MerchantRequiredMixin, MerchantDashboardShellContextMixin, BaseSiteView):
    template_name = "merchants/dashboard.html"
    merchant_section = "overview"
    merchant_title = "Merchant Home"
    merchant_intro = "Review live shop status, pending negotiation requests, alerts, and recent order activity."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        merchant = self.request.user.merchant_profile
        analytics = MerchantService.get_merchant_analytics(merchant)
        price_match_requests = list(
            PriceMatchRequest.objects.filter(merchant=merchant, status="pending")
            .select_related("product", "user")
            .order_by("-created_at")[:8]
        )
        orders = list(
            Order.objects.filter(items__merchant=merchant)
            .select_related("user")
            .prefetch_related("items", "items__product")
            .distinct()
            .order_by("-created_at")[:6]
        )
        notifications = list(self.request.user.notifications.order_by("-created_at")[:6])
        low_stock_alerts = MerchantProductService.get_low_stock_alerts(merchant)

        pricing_hint = None
        candidate_offer = (
            Offer.objects.filter(merchant=merchant, is_active=True).select_related("product").order_by("price").first()
        )
        if candidate_offer:
            pricing_hint = MerchantService.suggest_pricing(merchant, candidate_offer.product_id)

        context.update(
            {
                "merchant": merchant,
                "analytics": analytics,
                "merchant_stats": analytics.get("sales", {}),
                "merchant_overview": analytics.get("overview", {}),
                "price_match_stats": analytics.get("price_matches", {}),
                "price_match_requests": price_match_requests,
                "recent_orders": orders,
                "merchant_notifications": notifications,
                "low_stock_alerts": low_stock_alerts,
                "pricing_hint": pricing_hint,
            }
        )
        return context


class MerchantInventoryPageView(MerchantRequiredMixin, MerchantDashboardShellContextMixin, BaseSiteView):
    template_name = "merchants/inventory.html"
    merchant_section = "products"
    merchant_title = "Inventory Management"
    merchant_intro = "Manage real merchant listings, prices, stock, and product details that appear in search."

    def _inventory_queryset(self):
        merchant = self.request.user.merchant_profile
        queryset = Offer.objects.filter(merchant=merchant).select_related("product", "product__category", "product__brand")
        query = self.request.GET.get("q", "").strip()
        category_id = self.request.GET.get("category", "").strip()
        status_filter = self.request.GET.get("status", "all").strip()

        if query:
            queryset = queryset.filter(
                Q(product__name__icontains=query)
                | Q(product__barcode__icontains=query)
                | Q(product__brand__name__icontains=query)
            )
        if category_id:
            queryset = queryset.filter(product__category_id=category_id)
        if status_filter == "active":
            queryset = queryset.filter(is_active=True)
        elif status_filter == "inactive":
            queryset = queryset.filter(is_active=False)
        return queryset.order_by("-is_active", "product__name")

    def post(self, request, *args, **kwargs):
        merchant = request.user.merchant_profile
        action = request.POST.get("action", "").strip()
        offer_id = request.POST.get("offer_id")
        offer = (
            Offer.objects.filter(id=offer_id, merchant=merchant)
            .select_related("product", "product__category", "product__brand")
            .first()
        )
        if not offer:
            messages.error(request, "The selected inventory item could not be found.")
            return redirect("merchant_inventory")

        try:
            if action == "update_listing":
                name = request.POST.get("name", "").strip()
                category_id = request.POST.get("category_id", "").strip()
                barcode_raw = request.POST.get("barcode", "").strip()
                price = validate_price(request.POST.get("price"))
                original_price_raw = request.POST.get("original_price", "").strip()
                original_price = validate_price(original_price_raw) if original_price_raw else None
                stock_quantity = validate_stock_quantity(request.POST.get("stock_quantity"))
                delivery_time_hours = validate_delivery_time(request.POST.get("delivery_time_hours"))

                if not name:
                    raise ValidationError("Product name is required.")
                if original_price and original_price < price:
                    raise ValidationError("Original price must be greater than or equal to the current price.")

                category = offer.product.category
                if category_id:
                    category = Category.objects.filter(id=category_id).first()
                    if not category:
                        raise ValidationError("Select a valid category.")

                barcode = validate_barcode(barcode_raw) if barcode_raw else None
                if barcode and Product.objects.filter(barcode=barcode).exclude(id=offer.product_id).exists():
                    raise ValidationError("Another product already uses this barcode.")

                offer.product.name = name
                offer.product.category = category
                offer.product.barcode = barcode
                offer.product.save(update_fields=["name", "category", "barcode", "updated_at"])

                # Handle Image Upload for Update
                image_file = request.FILES.get("image")
                if image_file:
                    try:
                        fs = FileSystemStorage()
                        filename = fs.save(f"products/{image_file.name}", image_file)
                        offer.product.image_url = settings.MEDIA_URL + filename
                        offer.product.save(update_fields=["image_url", "updated_at"])
                    except Exception as img_err:
                        logger.error(f"Merchant inventory image upload error: {img_err}")


                offer.price = price
                offer.original_price = original_price
                offer.stock_quantity = stock_quantity
                offer.delivery_time_hours = delivery_time_hours
                offer.save(update_fields=["price", "original_price", "stock_quantity", "delivery_time_hours", "updated_at"])

                UserActivity.objects.create(
                    user=request.user,
                    activity_type="offer_updated",
                    product=offer.product,
                    merchant=merchant,
                    metadata={"offer_id": offer.id, "price": float(price), "stock_quantity": stock_quantity},
                )
                messages.success(request, "Inventory item updated successfully.")

            elif action == "deactivate_listing":
                offer.is_active = False
                offer.save(update_fields=["is_active", "updated_at"])
                UserActivity.objects.create(
                    user=request.user,
                    activity_type="offer_deactivated",
                    product=offer.product,
                    merchant=merchant,
                    metadata={"offer_id": offer.id},
                )
                messages.success(request, "Listing deactivated. It will no longer appear in search results.")

            elif action == "reactivate_listing":
                offer.is_active = True
                offer.save(update_fields=["is_active", "updated_at"])
                UserActivity.objects.create(
                    user=request.user,
                    activity_type="offer_reactivated",
                    product=offer.product,
                    merchant=merchant,
                    metadata={"offer_id": offer.id},
                )
                messages.success(request, "Listing reactivated successfully.")

            else:
                messages.error(request, "Unsupported inventory action.")
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))

        return redirect("merchant_inventory")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        merchant = self.request.user.merchant_profile
        offers = list(self._inventory_queryset())
        categories = list(Category.objects.order_by("name"))
        inventory_rows = []
        for offer in offers:
            competitor_count = Offer.objects.filter(product=offer.product, is_active=True).exclude(merchant=merchant).count()
            usage_count = (
                OrderItem.objects.filter(merchant=merchant, product=offer.product).aggregate(total=Sum("quantity"))["total"]
                or 0
            )
            inventory_rows.append(
                SimpleNamespace(
                    offer=offer,
                    product=offer.product,
                    competitor_count=competitor_count,
                    usage_count=usage_count,
                    is_low_stock=offer.stock_quantity <= 5,
                )
            )

        context.update(
            {
                "merchant": merchant,
                "categories": categories,
                "inventory_rows": inventory_rows,
                "inventory_summary": {
                    "total": len(inventory_rows),
                    "active": sum(1 for row in inventory_rows if row.offer.is_active),
                    "inactive": sum(1 for row in inventory_rows if not row.offer.is_active),
                    "low_stock": sum(1 for row in inventory_rows if row.is_low_stock),
                },
                "inventory_filters": {
                    "q": self.request.GET.get("q", "").strip(),
                    "category": self.request.GET.get("category", "").strip(),
                    "status": self.request.GET.get("status", "all").strip(),
                },
            }
        )
        return context


class MerchantAddProductPageView(MerchantRequiredMixin, MerchantDashboardShellContextMixin, BaseSiteView):
    template_name = "merchants/add_product.html"
    merchant_section = "add_product"
    merchant_title = "Add Product"
    merchant_intro = "Create a real merchant listing and attach it to the search catalog with validated pricing and stock."

    def _form_values(self):
        return getattr(
            self,
            "_merchant_add_form_values",
            {
                "name": "",
                "category_id": "",
                "brand": "",
                "barcode": "",
                "description": "",
                "price": "",
                "original_price": "",
                "stock_quantity": "1",
                "delivery_time_hours": "24",
            },
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "categories": Category.objects.order_by("name"),
                "add_product_form_values": self._form_values(),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        merchant = request.user.merchant_profile
        form_values = {
            "name": request.POST.get("name", "").strip(),
            "category_id": request.POST.get("category_id", "").strip() or request.POST.get("category", "").strip(),
            "brand": request.POST.get("brand", "").strip(),
            "barcode": request.POST.get("barcode", "").strip(),
            "description": request.POST.get("description", "").strip(),
            "price": request.POST.get("price", "").strip(),
            "original_price": request.POST.get("original_price", "").strip(),
            "stock_quantity": request.POST.get("stock_quantity", "").strip() or "1",
            "delivery_time_hours": request.POST.get("delivery_time_hours", "").strip() or "24",
        }
        self._merchant_add_form_values = form_values

        try:
            if not form_values["name"]:
                raise ValidationError("Product name is required.")
            category = Category.objects.filter(id=form_values["category_id"]).first()
            if not category:
                raise ValidationError("Select a valid category.")

            price = validate_price(form_values["price"])
            original_price = validate_price(form_values["original_price"]) if form_values["original_price"] else None
            if original_price and original_price < price:
                raise ValidationError("Original price must be greater than or equal to the current price.")

            stock_quantity = validate_stock_quantity(form_values["stock_quantity"])
            delivery_time_hours = validate_delivery_time(form_values["delivery_time_hours"])
            barcode = validate_barcode(form_values["barcode"]) if form_values["barcode"] else None
            brand = None
            if form_values["brand"]:
                brand = Brand.objects.filter(name__iexact=form_values["brand"]).first()
                if not brand:
                    brand = Brand.objects.create(name=form_values["brand"])

            product = None
            if barcode:
                product = Product.objects.filter(barcode=barcode).first()
            if product is None:
                product = Product.objects.filter(
                    name__iexact=form_values["name"],
                    category=category,
                    brand=brand,
                ).first()

            if product is None:
                product = Product.objects.create(
                    name=form_values["name"],
                    barcode=barcode,
                    category=category,
                    brand=brand,
                    description=form_values["description"],
                )
            else:
                updated_fields = []
                if barcode and product.barcode != barcode:
                    product.barcode = barcode
                    updated_fields.append("barcode")
                if product.category_id != category.id:
                    product.category = category
                    updated_fields.append("category")
                if brand and product.brand_id != brand.id:
                    product.brand = brand
                    updated_fields.append("brand")
                if form_values["description"] and not product.description:
                    product.description = form_values["description"]
                    updated_fields.append("description")
                if updated_fields:
                    updated_fields.append("updated_at")
                    product.save(update_fields=updated_fields)

            # Handle Image Upload
            image_file = request.FILES.get("image")
            if image_file:
                try:
                    fs = FileSystemStorage()
                    # Ensure path exists or let FSS handle it
                    filename = fs.save(f"products/{image_file.name}", image_file)
                    product.image_url = settings.MEDIA_URL + filename
                    product.save(update_fields=["image_url", "updated_at"])
                except Exception as img_err:
                    logger.error(f"Merchant image upload error: {img_err}")
                    # Non-fatal, just log and continue


            if Offer.objects.filter(merchant=merchant, product=product).exists():
                raise ValidationError("This product is already listed in your shop inventory.")

            offer = Offer.objects.create(
                product=product,
                merchant=merchant,
                price=price,
                original_price=original_price,
                delivery_time_hours=delivery_time_hours,
                stock_quantity=stock_quantity,
                is_active=True,
            )
            UserActivity.objects.create(
                user=request.user,
                activity_type="product_added",
                product=product,
                merchant=merchant,
                metadata={"offer_id": offer.id, "price": float(price)},
            )
            messages.success(request, "Product added to merchant inventory successfully.")
            return redirect("merchant_inventory")
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
            return self.render_to_response(self.get_context_data())


class MerchantPriceMatchRequestsPageView(MerchantRequiredMixin, MerchantDashboardShellContextMixin, BaseSiteView):
    template_name = "merchants/price_match_requests.html"
    merchant_section = "requests"
    merchant_title = "Price-Match Requests"
    merchant_intro = "Review customer negotiation requests, approve or reject them, and notify the customer with a real record."

    def post(self, request, *args, **kwargs):
        merchant = request.user.merchant_profile
        request_id = request.POST.get("request_id")
        decision = request.POST.get("decision", "").strip().lower()
        response_message = request.POST.get("response_message", "").strip()

        price_request = (
            PriceMatchRequest.objects.filter(id=request_id, merchant=merchant, status="pending")
            .select_related("product", "user")
            .first()
        )
        if not price_request:
            messages.error(request, "The selected price-match request could not be found.")
            return redirect("merchant_requests")

        try:
            if decision not in {"approved", "rejected"}:
                raise ValidationError("Choose approve or reject for the request.")

            if decision == "approved":
                expires_at = timezone.now() + timedelta(hours=2)
                coupon_code = f"DEAL{price_request.id:05d}"
                final_message = response_message or (
                    f"Deal-Lock approved. Coupon {coupon_code} is valid until {expires_at.strftime('%d %b %Y %I:%M %p')}."
                )
                price_request.status = "approved"
                price_request.expires_at = expires_at
                price_request.response_message = final_message
                notification_title = "Deal-Lock approved"
            else:
                final_message = response_message or "The merchant rejected your price-match request."
                price_request.status = "rejected"
                price_request.expires_at = None
                price_request.response_message = final_message
                notification_title = "Price-match request rejected"

            price_request.save(update_fields=["status", "expires_at", "response_message", "updated_at"])

            Notification.objects.create(
                user=price_request.user,
                title=notification_title,
                message=final_message,
                notification_type="price_match",
            )
            UserActivity.objects.create(
                user=request.user,
                activity_type="price_match_handled",
                product=price_request.product,
                merchant=merchant,
                metadata={"request_id": price_request.id, "status": price_request.status},
            )
            messages.success(request, f"Request {price_request.id} marked as {price_request.status}.")
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))

        return redirect("merchant_requests")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        merchant = self.request.user.merchant_profile
        status_filter = self.request.GET.get("status", "pending").strip()
        queryset = PriceMatchRequest.objects.filter(merchant=merchant).select_related("product", "user")
        if status_filter != "all":
            queryset = queryset.filter(status=status_filter)
        requests = list(queryset.order_by("-created_at"))
        request_rows = []
        for item in requests:
            merchant_offer = Offer.objects.filter(merchant=merchant, product=item.product, is_active=True).first()
            request_rows.append(SimpleNamespace(record=item, merchant_offer=merchant_offer))

        context.update(
            {
                "request_rows": request_rows,
                "request_filters": {"status": status_filter},
                "request_summary": {
                    "total": PriceMatchRequest.objects.filter(merchant=merchant).count(),
                    "pending": PriceMatchRequest.objects.filter(merchant=merchant, status="pending").count(),
                    "approved": PriceMatchRequest.objects.filter(merchant=merchant, status="approved").count(),
                    "rejected": PriceMatchRequest.objects.filter(merchant=merchant, status="rejected").count(),
                },
            }
        )
        return context


class MerchantDealsPageView(MerchantRequiredMixin, MerchantDashboardShellContextMixin, BaseSiteView):
    template_name = "merchants/deals.html"
    merchant_section = "deals"
    merchant_title = "Deal Management"
    merchant_intro = "Track active discounted offers, approved deal-lock requests, and expire them when they are no longer valid."

    def post(self, request, *args, **kwargs):
        merchant = request.user.merchant_profile
        action = request.POST.get("action", "").strip()

        try:
            if action in {"expire_offer", "reactivate_offer"}:
                offer = Offer.objects.filter(id=request.POST.get("offer_id"), merchant=merchant).select_related("product").first()
                if not offer:
                    raise ValidationError("Offer not found.")
                offer.is_active = action == "reactivate_offer"
                offer.save(update_fields=["is_active", "updated_at"])
                UserActivity.objects.create(
                    user=request.user,
                    activity_type="deal_status_changed",
                    product=offer.product,
                    merchant=merchant,
                    metadata={"offer_id": offer.id, "is_active": offer.is_active},
                )
                messages.success(request, "Deal status updated successfully.")

            elif action == "expire_request":
                request_record = PriceMatchRequest.objects.filter(
                    id=request.POST.get("request_id"),
                    merchant=merchant,
                    status="approved",
                ).select_related("product", "user").first()
                if not request_record:
                    raise ValidationError("Approved deal-lock request not found.")
                request_record.status = "expired"
                request_record.expires_at = timezone.now()
                request_record.save(update_fields=["status", "expires_at", "updated_at"])
                Notification.objects.create(
                    user=request_record.user,
                    title="Deal-Lock expired",
                    message=f"The approved deal for {request_record.product.name} has expired.",
                    notification_type="price_match",
                )
                messages.success(request, "Approved deal-lock request marked as expired.")
            else:
                messages.error(request, "Unsupported deal action.")
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))

        return redirect("merchant_deals")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        merchant = self.request.user.merchant_profile
        offers = list(
            Offer.objects.filter(merchant=merchant)
            .select_related("product", "product__category")
            .order_by("-is_active", "price")
        )
        approved_requests = list(
            PriceMatchRequest.objects.filter(merchant=merchant, status="approved")
            .select_related("product", "user")
            .order_by("-updated_at")
        )
        offer_rows = []
        for offer in offers:
            usage_count = (
                OrderItem.objects.filter(merchant=merchant, product=offer.product).aggregate(total=Sum("quantity"))["total"]
                or 0
            )
            offer_rows.append(SimpleNamespace(offer=offer, usage_count=usage_count))

        context.update(
            {
                "offer_rows": offer_rows,
                "approved_requests": approved_requests,
                "deal_summary": {
                    "active_offers": Offer.objects.filter(merchant=merchant, is_active=True).count(),
                    "inactive_offers": Offer.objects.filter(merchant=merchant, is_active=False).count(),
                    "approved_requests": len(approved_requests),
                    "expired_requests": PriceMatchRequest.objects.filter(merchant=merchant, status="expired").count(),
                },
            }
        )
        return context


class MerchantDeliverySettingsPageView(MerchantRequiredMixin, MerchantDashboardShellContextMixin, BaseSiteView):
    template_name = "merchants/delivery.html"
    merchant_section = "delivery"
    merchant_title = "Hyperlocal Delivery"
    merchant_intro = "Control delivery availability and radius. Offer-level delivery time remains part of each active listing."

    def post(self, request, *args, **kwargs):
        merchant = request.user.merchant_profile
        try:
            delivery_enabled = request.POST.get("delivery_enabled") == "on"
            delivery_radius_raw = request.POST.get("delivery_radius_km", "").strip() or "0"
            delivery_radius = int(delivery_radius_raw)
            if delivery_enabled and delivery_radius <= 0:
                raise ValidationError("Delivery radius must be greater than 0 when delivery is enabled.")
            if delivery_radius < 0:
                raise ValidationError("Delivery radius cannot be negative.")

            merchant.delivery_enabled = delivery_enabled
            merchant.delivery_radius_km = delivery_radius
            merchant.save(update_fields=["delivery_enabled", "delivery_radius_km", "updated_at"])

            apply_delivery_time = request.POST.get("apply_delivery_time_to_offers") == "on"
            default_delivery_time_raw = request.POST.get("default_delivery_time_hours", "").strip()
            updated_offers = 0
            if apply_delivery_time and default_delivery_time_raw:
                delivery_time_hours = validate_delivery_time(default_delivery_time_raw)
                updated_offers = Offer.objects.filter(merchant=merchant, is_active=True).update(
                    delivery_time_hours=delivery_time_hours
                )

            UserActivity.objects.create(
                user=request.user,
                activity_type="delivery_settings_updated",
                merchant=merchant,
                metadata={
                    "delivery_enabled": delivery_enabled,
                    "delivery_radius_km": delivery_radius,
                    "updated_offers": updated_offers,
                },
            )
            messages.success(request, "Delivery settings updated successfully.")
            return redirect("merchant_delivery")
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
            return self.render_to_response(self.get_context_data())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        merchant = self.request.user.merchant_profile
        offer_stats = Offer.objects.filter(merchant=merchant, is_active=True).aggregate(
            avg_delivery_time=Avg("delivery_time_hours"),
            offer_count=Count("id"),
        )
        context.update(
            {
                "merchant": merchant,
                "delivery_stats": {
                    "active_offer_count": offer_stats["offer_count"] or 0,
                    "average_delivery_time": round(float(offer_stats["avg_delivery_time"] or 0), 2),
                },
            }
        )
        return context


class MerchantAnalyticsPageView(MerchantRequiredMixin, MerchantDashboardShellContextMixin, BaseSiteView):
    template_name = "merchants/analytics.html"
    merchant_section = "analytics"
    merchant_title = "Analytics"
    merchant_intro = "Review merchant performance across offers, orders, requests, and recent activity."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        merchant = self.request.user.merchant_profile
        analytics = MerchantService.get_merchant_analytics(merchant)
        performance = MerchantService.get_merchant_performance(merchant, days=30)
        context.update(
            {
                "merchant": merchant,
                "analytics": analytics,
                "performance": performance,
                "recent_notifications": list(self.request.user.notifications.order_by("-created_at")[:5]),
            }
        )
        return context


class MerchantNotificationsPageView(MerchantRequiredMixin, MerchantDashboardShellContextMixin, BaseSiteView):
    template_name = "merchants/notifications.html"
    merchant_section = "notifications"
    merchant_title = "Notifications"
    merchant_intro = "Track merchant alerts for new orders, deal requests, and system updates."

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "").strip()
        if action == "mark_all_read":
            request.user.notifications.filter(is_read=False).update(is_read=True)
            messages.success(request, "All merchant notifications marked as read.")
        elif action == "mark_read":
            notification = request.user.notifications.filter(id=request.POST.get("notification_id")).first()
            if notification:
                notification.is_read = True
                notification.save(update_fields=["is_read"])
                messages.success(request, "Notification marked as read.")
        return redirect("merchant_notifications")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filter_value = self.request.GET.get("filter", "all").strip()
        notifications = self.request.user.notifications.all()
        if filter_value == "unread":
            notifications = notifications.filter(is_read=False)
        context.update(
            {
                "merchant_notifications": list(notifications.order_by("-created_at")[:50]),
                "notification_filter": filter_value,
            }
        )
        return context


class MerchantProfilePageView(MerchantRequiredMixin, MerchantDashboardShellContextMixin, BaseSiteView):
    template_name = "merchants/profile.html"
    merchant_section = "profile"
    merchant_title = "Merchant Profile"
    merchant_intro = "Update shop details, account credentials, and merchant location with the same backend validation rules."

    def _profile_form_values(self):
        merchant = self.request.user.merchant_profile
        return getattr(
            self,
            "_merchant_profile_form_values",
            {
                "first_name": self.request.user.first_name,
                "last_name": self.request.user.last_name,
                "email": self.request.user.email,
                "phone": self.request.user.phone or "",
                "shop_name": merchant.shop_name,
                "business_category": merchant.business_category or "",
                "address": merchant.address or "",
                "gstin": merchant.gstin or "",
                "location_lat": merchant.location_lat or "",
                "location_lng": merchant.location_lng or "",
            },
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["merchant_profile_form_values"] = self._profile_form_values()
        return context

    def post(self, request, *args, **kwargs):
        user = request.user
        merchant = request.user.merchant_profile
        form_values = {
            "first_name": request.POST.get("first_name", "").strip(),
            "last_name": request.POST.get("last_name", "").strip(),
            "email": request.POST.get("email", "").strip().lower(),
            "phone": request.POST.get("phone", "").strip(),
            "shop_name": request.POST.get("shop_name", "").strip(),
            "business_category": request.POST.get("business_category", "").strip(),
            "address": request.POST.get("address", "").strip(),
            "gstin": request.POST.get("gstin", "").strip(),
            "location_lat": request.POST.get("location_lat", "").strip(),
            "location_lng": request.POST.get("location_lng", "").strip(),
        }
        self._merchant_profile_form_values = form_values

        current_password = request.POST.get("current_password", "")
        new_password = request.POST.get("new_password", "")
        confirm_new_password = request.POST.get("confirm_new_password", "")

        try:
            if not form_values["first_name"] or not form_values["last_name"]:
                raise ValidationError("First name and last name are required.")
            if not form_values["email"]:
                raise ValidationError("Email is required.")
            if not form_values["shop_name"]:
                raise ValidationError("Shop name is required.")
            if not form_values["business_category"]:
                raise ValidationError("Business category is required.")
            if not form_values["address"]:
                raise ValidationError("Shop address is required.")
            if User.objects.filter(email__iexact=form_values["email"]).exclude(pk=user.pk).exists():
                raise ValidationError("Another account already uses this email address.")

            normalized_phone = validate_phone_number(form_values["phone"]) if form_values["phone"] else ""
            normalized_gstin = validate_gstin(form_values["gstin"]) if form_values["gstin"] else None
            if not form_values["location_lat"] or not form_values["location_lng"]:
                raise ValidationError("Merchant latitude and longitude are required.")
            validate_location(form_values["location_lat"], form_values["location_lng"])
            normalized_lat = Decimal(form_values["location_lat"])
            normalized_lng = Decimal(form_values["location_lng"])

            password_change_requested = any([current_password, new_password, confirm_new_password])
            if password_change_requested:
                if not current_password or not new_password or not confirm_new_password:
                    raise ValidationError("Complete all password fields to change your password.")
                if not user.check_password(current_password):
                    raise ValidationError("Current password is incorrect.")
                if new_password != confirm_new_password:
                    raise ValidationError("New password and confirmation do not match.")
                validate_strong_password(new_password)

            user.first_name = form_values["first_name"]
            user.last_name = form_values["last_name"]
            user.email = form_values["email"]
            user.phone = normalized_phone
            if password_change_requested:
                user.set_password(new_password)
            user.save()

            merchant.shop_name = form_values["shop_name"]
            merchant.business_category = form_values["business_category"]
            merchant.address = form_values["address"]
            merchant.gstin = normalized_gstin
            merchant.location_lat = normalized_lat
            merchant.location_lng = normalized_lng
            merchant.save()

            if password_change_requested:
                update_session_auth_hash(request, user)

            messages.success(request, "Merchant profile updated successfully.")
            return redirect("merchant_profile_dashboard")
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
            return self.render_to_response(self.get_context_data())


def merchant_dashboard_legacy_redirect(request):
    return redirect("merchant_dashboard")


class AdminDashboardShellContextMixin:
    admin_section = "overview"
    admin_title = "Admin Dashboard"
    admin_intro = "Monitor users, merchants, products, deals, datasets, ranking controls, and system health."

    def get_admin_navigation(self):
        items = [
            ("overview", "admin_dashboard", "fa-gauge-high", "Overview"),
            ("users", "admin_users", "fa-users", "Users"),
            ("merchants", "admin_merchants", "fa-store", "Merchants"),
            ("products", "admin_products", "fa-boxes-stacked", "Products"),
            ("deals", "admin_deals", "fa-tags", "Deals"),
            ("data", "admin_data", "fa-database", "Data"),
            ("ml", "admin_ml", "fa-brain", "ML Control"),
            ("notifications", "admin_notifications", "fa-bell", "Notifications"),
            ("analytics", "admin_analytics", "fa-chart-line", "Analytics"),
            ("logs", "admin_logs", "fa-shield-halved", "Logs"),
            ("profile", "admin_profile", "fa-user-gear", "Profile"),
            ("logout", "logout", "fa-right-from-bracket", "Logout"),
        ]
        return [
            SimpleNamespace(
                key=key,
                url=reverse(route_name),
                icon=icon,
                label=label,
                active=(key == self.admin_section),
            )
            for key, route_name, icon, label in items
        ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        system_health = AdminService.get_system_health()
        admin_user = self.request.user
        context.update(
            {
                "admin_dashboard_nav": self.get_admin_navigation(),
                "admin_dashboard_title": self.admin_title,
                "admin_dashboard_intro": self.admin_intro,
                "admin_shell": SimpleNamespace(
                    name=admin_user.get_full_name() or admin_user.username,
                    email=admin_user.email,
                    role="Platform Administrator",
                ),
                "admin_shell_stats": {
                    "total_users": User.objects.filter(is_staff=False).count(),
                    "pending_merchants": Merchant.objects.filter(verified=False).count(),
                    "active_offers": Offer.objects.filter(is_active=True).count(),
                    "unread_notifications": admin_user.notifications.filter(is_read=False).count(),
                    "system_status": system_health.get("overall_status", "unknown"),
                    "recent_activity": system_health.get("recent_activity_count", 0),
                },
            }
        )
        return context


class AdminDashboardPageView(StaffRequiredMixin, AdminDashboardShellContextMixin, BaseSiteView):
    template_name = "admin_panel/dashboard.html"
    admin_section = "overview"
    admin_title = "Admin Dashboard"
    admin_intro = "Use the sidebar to approve merchants, govern catalog data, tune the ranking engine, and monitor system health."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        dashboard = AdminService.get_dashboard_data()
        system_health = dashboard.get("system_health", {})
        storage = system_health.get("storage_usage", {})
        context.update(
            {
                "dashboard": dashboard,
                "overview": dashboard.get("overview", {}),
                "user_stats": dashboard.get("user_stats", {}),
                "merchant_stats": dashboard.get("merchant_stats", {}),
                "product_stats": dashboard.get("product_stats", {}),
                "offer_stats": dashboard.get("offer_stats", {}),
                "price_match_stats": dashboard.get("price_match_stats", {}),
                "pending_merchant_approvals": Merchant.objects.filter(verified=False).count(),
                "active_deals_count": Offer.objects.filter(is_active=True).count(),
                "system_activities": list(
                    UserActivity.objects.select_related("user", "product", "merchant").order_by("-created_at")[:12]
                ),
                "system_health": system_health,
                "storage_usage_mb": round(storage.get("total_size_bytes", 0) / (1024 * 1024), 2),
            }
        )
        return context


class AdminUsersPageView(StaffRequiredMixin, AdminDashboardShellContextMixin, BaseSiteView):
    template_name = "admin_panel/users.html"
    admin_section = "users"
    admin_title = "User Management"
    admin_intro = "Search platform accounts, adjust account status, and enforce access controls without bypassing Django validation."

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "").strip()
        target_user = User.objects.filter(id=request.POST.get("user_id")).first()
        if not target_user:
            messages.error(request, "Selected user could not be found.")
            return redirect("admin_users")

        if target_user.pk == request.user.pk and action in {"deactivate", "soft_delete"}:
            messages.error(request, "You cannot deactivate or delete your own admin account from this screen.")
            return redirect("admin_users")

        try:
            if action == "activate":
                target_user.is_active = True
                target_user.save(update_fields=["is_active"])
                messages.success(request, f"{target_user.email} activated.")
            elif action == "deactivate":
                target_user.is_active = False
                target_user.save(update_fields=["is_active"])
                messages.success(request, f"{target_user.email} deactivated.")
            elif action == "verify":
                target_user.is_verified = True
                target_user.save(update_fields=["is_verified"])
                if target_user.is_merchant and hasattr(target_user, "merchant_profile"):
                    target_user.merchant_profile.verified = True
                    target_user.merchant_profile.save(update_fields=["verified", "updated_at"])
                messages.success(request, f"{target_user.email} marked as verified.")
            elif action == "unverify":
                target_user.is_verified = False
                target_user.save(update_fields=["is_verified"])
                if target_user.is_merchant and hasattr(target_user, "merchant_profile"):
                    target_user.merchant_profile.verified = False
                    target_user.merchant_profile.save(update_fields=["verified", "updated_at"])
                messages.success(request, f"{target_user.email} marked as unverified.")
            elif action == "soft_delete":
                target_user.is_active = False
                target_user.is_verified = False
                target_user.save(update_fields=["is_active", "is_verified"])
                if target_user.is_merchant and hasattr(target_user, "merchant_profile"):
                    target_user.merchant_profile.verified = False
                    target_user.merchant_profile.save(update_fields=["verified", "updated_at"])
                messages.success(request, f"{target_user.email} was soft-disabled.")
            else:
                messages.error(request, "Unsupported user action.")
                return redirect("admin_users")

            UserActivity.objects.create(
                user=request.user,
                activity_type="admin_user_action",
                metadata={"target_user_id": target_user.id, "action": action},
            )
        except Exception as exc:
            logger.error("Admin user action failed: %s", exc)
            messages.error(request, "User action failed.")

        return redirect("admin_users")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filters = {
            "q": self.request.GET.get("q", "").strip(),
            "role": self.request.GET.get("role", "all").strip(),
            "status": self.request.GET.get("status", "all").strip(),
            "verified": self.request.GET.get("verified", "all").strip(),
        }
        queryset = User.objects.order_by("-date_joined")
        if filters["q"]:
            queryset = queryset.filter(
                Q(username__icontains=filters["q"])
                | Q(email__icontains=filters["q"])
                | Q(first_name__icontains=filters["q"])
                | Q(last_name__icontains=filters["q"])
            )
        if filters["role"] == "customer":
            queryset = queryset.filter(is_staff=False, is_merchant=False)
        elif filters["role"] == "merchant":
            queryset = queryset.filter(is_merchant=True)
        elif filters["role"] == "admin":
            queryset = queryset.filter(is_staff=True)
        if filters["status"] == "active":
            queryset = queryset.filter(is_active=True)
        elif filters["status"] == "inactive":
            queryset = queryset.filter(is_active=False)
        if filters["verified"] == "verified":
            queryset = queryset.filter(is_verified=True)
        elif filters["verified"] == "unverified":
            queryset = queryset.filter(is_verified=False)

        users_page = Paginator(queryset, 25).get_page(self.request.GET.get("page"))
        context.update(
            {
                "users_page": users_page,
                "user_filters": filters,
                "user_summary": {
                    "total": User.objects.count(),
                    "customers": User.objects.filter(is_staff=False, is_merchant=False).count(),
                    "merchants": User.objects.filter(is_merchant=True).count(),
                    "admins": User.objects.filter(is_staff=True).count(),
                    "active": User.objects.filter(is_active=True).count(),
                    "inactive": User.objects.filter(is_active=False).count(),
                },
            }
        )
        return context


class AdminMerchantsPageView(StaffRequiredMixin, AdminDashboardShellContextMixin, BaseSiteView):
    template_name = "admin_panel/merchants.html"
    admin_section = "merchants"
    admin_title = "Merchant Verification"
    admin_intro = "Review shopkeepers, approve verified merchants, suspend risky stores, and keep the local marketplace trustworthy."

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "").strip()
        merchant = Merchant.objects.select_related("user").filter(id=request.POST.get("merchant_id")).first()
        if not merchant:
            messages.error(request, "Selected merchant could not be found.")
            return redirect("admin_merchants")

        try:
            if action == "approve":
                merchant.verified = True
                merchant.user.is_verified = True
                merchant.user.is_active = True
                merchant.user.save(update_fields=["is_verified", "is_active"])
                merchant.save(update_fields=["verified", "updated_at"])
                Notification.objects.create(
                    user=merchant.user,
                    title="Merchant account approved",
                    message="Your merchant account is approved and now visible in DealSphere search results.",
                    notification_type="general",
                )
                messages.success(request, f"{merchant.shop_name} approved.")
            elif action == "reject":
                merchant.verified = False
                merchant.user.is_verified = False
                merchant.user.is_active = False
                merchant.user.save(update_fields=["is_verified", "is_active"])
                merchant.save(update_fields=["verified", "updated_at"])
                Notification.objects.create(
                    user=merchant.user,
                    title="Merchant account rejected",
                    message="Your merchant account was not approved. Contact the admin team for review.",
                    notification_type="general",
                )
                messages.success(request, f"{merchant.shop_name} rejected and disabled.")
            elif action == "suspend":
                merchant.user.is_active = False
                merchant.user.save(update_fields=["is_active"])
                messages.success(request, f"{merchant.shop_name} suspended.")
            elif action == "reactivate":
                merchant.user.is_active = True
                merchant.user.save(update_fields=["is_active"])
                messages.success(request, f"{merchant.shop_name} reactivated.")
            else:
                messages.error(request, "Unsupported merchant action.")
                return redirect("admin_merchants")

            UserActivity.objects.create(
                user=request.user,
                activity_type="admin_merchant_action",
                merchant=merchant,
                metadata={"merchant_id": merchant.id, "action": action},
            )
        except Exception as exc:
            logger.error("Admin merchant action failed: %s", exc)
            messages.error(request, "Merchant action failed.")

        return redirect("admin_merchants")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filters = {
            "q": self.request.GET.get("q", "").strip(),
            "verification": self.request.GET.get("verification", "all").strip(),
            "status": self.request.GET.get("status", "all").strip(),
        }
        queryset = Merchant.objects.select_related("user").annotate(product_count=Count("offers")).order_by("-created_at")
        if filters["q"]:
            queryset = queryset.filter(
                Q(shop_name__icontains=filters["q"])
                | Q(user__email__icontains=filters["q"])
                | Q(user__first_name__icontains=filters["q"])
                | Q(user__last_name__icontains=filters["q"])
            )
        if filters["verification"] == "verified":
            queryset = queryset.filter(verified=True)
        elif filters["verification"] == "pending":
            queryset = queryset.filter(verified=False)
        if filters["status"] == "active":
            queryset = queryset.filter(user__is_active=True)
        elif filters["status"] == "suspended":
            queryset = queryset.filter(user__is_active=False)

        merchants_page = Paginator(queryset, 20).get_page(self.request.GET.get("page"))
        context.update(
            {
                "merchants_page": merchants_page,
                "merchant_filters": filters,
                "merchant_summary": {
                    "total": Merchant.objects.count(),
                    "verified": Merchant.objects.filter(verified=True).count(),
                    "pending": Merchant.objects.filter(verified=False).count(),
                    "suspended": Merchant.objects.filter(user__is_active=False).count(),
                },
            }
        )
        return context


class AdminProductsPageView(StaffRequiredMixin, AdminDashboardShellContextMixin, BaseSiteView):
    template_name = "admin_panel/products.html"
    admin_section = "products"
    admin_title = "Product Management"
    admin_intro = "Inspect catalog rows from datasets, correct metadata, and remove unsafe products only when they are not referenced by live commerce records."

    def _editing_form_values(self, product):
        if hasattr(self, "_editing_product_form_values"):
            return self._editing_product_form_values
        if not product:
            return {}
        return {
            "product_id": product.id,
            "name": product.name,
            "barcode": product.barcode or "",
            "category": product.category.name if product.category else "",
            "brand": product.brand.name if product.brand else "",
            "description": product.description or "",
            "amazon_price": product.amazon_price or "",
            "flipkart_price": product.flipkart_price or "",
            "amazon_rating": product.amazon_rating or "",
            "flipkart_rating": product.flipkart_rating or "",
            "amazon_url": product.amazon_url or "",
            "flipkart_url": product.flipkart_url or "",
            "image_url": product.image_url or "",
        }

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "").strip()
        product = Product.objects.select_related("category", "brand").filter(id=request.POST.get("product_id")).first()
        if not product:
            messages.error(request, "Selected product could not be found.")
            return redirect("admin_products")

        try:
            if action == "delete":
                if CartItem.objects.filter(product=product).exists() or OrderItem.objects.filter(product=product).exists():
                    raise ValidationError("This product is referenced by cart or order records and cannot be deleted safely.")
                if PriceMatchRequest.objects.filter(product=product).exists():
                    raise ValidationError("This product has price-match requests and cannot be deleted safely.")
                product_name = product.name
                product.delete()
                UserActivity.objects.create(
                    user=request.user,
                    activity_type="admin_product_deleted",
                    metadata={"product_name": product_name},
                )
                messages.success(request, f"{product_name} deleted.")
                return redirect("admin_products")

            if action != "update":
                raise ValidationError("Unsupported product action.")

            form_values = {
                "product_id": product.id,
                "name": request.POST.get("name", "").strip(),
                "barcode": request.POST.get("barcode", "").strip(),
                "category": request.POST.get("category", "").strip(),
                "brand": request.POST.get("brand", "").strip(),
                "description": request.POST.get("description", "").strip(),
                "amazon_price": request.POST.get("amazon_price", "").strip(),
                "flipkart_price": request.POST.get("flipkart_price", "").strip(),
                "amazon_rating": request.POST.get("amazon_rating", "").strip(),
                "flipkart_rating": request.POST.get("flipkart_rating", "").strip(),
                "amazon_url": request.POST.get("amazon_url", "").strip(),
                "flipkart_url": request.POST.get("flipkart_url", "").strip(),
                "image_url": request.POST.get("image_url", "").strip(),
            }
            self._editing_product_form_values = form_values

            if not form_values["name"]:
                raise ValidationError("Product name is required.")
            if form_values["barcode"]:
                validate_barcode(form_values["barcode"])
                barcode_conflict = Product.objects.filter(barcode=form_values["barcode"]).exclude(pk=product.pk).exists()
                if barcode_conflict:
                    raise ValidationError("Another product already uses that barcode.")

            category = None
            if form_values["category"]:
                category = Category.objects.filter(name__iexact=form_values["category"]).first()
                if not category:
                    category = Category.objects.create(name=form_values["category"])
            brand = None
            if form_values["brand"]:
                brand = Brand.objects.filter(name__iexact=form_values["brand"]).first()
                if not brand:
                    brand = Brand.objects.create(name=form_values["brand"])

            amazon_price = validate_price(form_values["amazon_price"]) if form_values["amazon_price"] else None
            flipkart_price = validate_price(form_values["flipkart_price"]) if form_values["flipkart_price"] else None

            amazon_rating = None
            if form_values["amazon_rating"]:
                amazon_rating = float(form_values["amazon_rating"])
                if amazon_rating < 0 or amazon_rating > 5:
                    raise ValidationError("Amazon rating must stay between 0 and 5.")
            flipkart_rating = None
            if form_values["flipkart_rating"]:
                flipkart_rating = float(form_values["flipkart_rating"])
                if flipkart_rating < 0 or flipkart_rating > 5:
                    raise ValidationError("Flipkart rating must stay between 0 and 5.")

            product.name = form_values["name"]
            product.barcode = form_values["barcode"] or None
            product.category = category
            product.brand = brand
            product.description = form_values["description"] or None
            product.amazon_price = amazon_price
            product.flipkart_price = flipkart_price
            product.amazon_rating = amazon_rating
            product.flipkart_rating = flipkart_rating
            product.amazon_url = form_values["amazon_url"] or None
            product.flipkart_url = form_values["flipkart_url"] or None
            product.image_url = form_values["image_url"] or None
            product.save()

            UserActivity.objects.create(
                user=request.user,
                activity_type="admin_product_updated",
                product=product,
                metadata={"product_id": product.id},
            )
            messages.success(request, f"{product.name} updated.")
            return redirect(f"{reverse('admin_products')}?edit={product.id}")
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
            return self.render_to_response(self.get_context_data())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filters = {
            "q": self.request.GET.get("q", "").strip(),
            "category": self.request.GET.get("category", "").strip(),
            "brand": self.request.GET.get("brand", "").strip(),
        }
        queryset = Product.objects.select_related("category", "brand").annotate(offer_count=Count("offers")).order_by("-created_at")
        if filters["q"]:
            queryset = queryset.filter(
                Q(name__icontains=filters["q"])
                | Q(barcode__icontains=filters["q"])
                | Q(description__icontains=filters["q"])
            )
        if filters["category"]:
            queryset = queryset.filter(category__name__icontains=filters["category"])
        if filters["brand"]:
            queryset = queryset.filter(brand__name__icontains=filters["brand"])

        editing_product = None
        edit_id = self.request.GET.get("edit")
        if edit_id:
            editing_product = Product.objects.select_related("category", "brand").filter(id=edit_id).first()

        products_page = Paginator(queryset, 20).get_page(self.request.GET.get("page"))
        duplicate_products = (
            Product.objects.values("name")
            .annotate(total=Count("id"))
            .filter(total__gt=1)
            .order_by("-total", "name")[:10]
        )
        context.update(
            {
                "products_page": products_page,
                "product_filters": filters,
                "editing_product": editing_product,
                "editing_product_form_values": self._editing_form_values(editing_product),
                "product_summary": {
                    "total": Product.objects.count(),
                    "with_barcode": Product.objects.exclude(barcode__isnull=True).exclude(barcode="").count(),
                    "with_offers": Product.objects.filter(offers__is_active=True).distinct().count(),
                    "duplicates": duplicate_products.count(),
                },
                "duplicate_products": list(duplicate_products),
            }
        )
        return context


class AdminDealsPageView(StaffRequiredMixin, AdminDashboardShellContextMixin, BaseSiteView):
    template_name = "admin_panel/deals.html"
    admin_section = "deals"
    admin_title = "Deal & Price-Match Management"
    admin_intro = "Track negotiations, review approved deal-locks, and disable suspicious local offers from one screen."

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "").strip()
        try:
            if action in {"cancel_offer", "reactivate_offer"}:
                offer = Offer.objects.select_related("product", "merchant").filter(id=request.POST.get("offer_id")).first()
                if not offer:
                    raise ValidationError("Selected offer could not be found.")
                offer.is_active = action == "reactivate_offer"
                offer.save(update_fields=["is_active", "updated_at"])
                UserActivity.objects.create(
                    user=request.user,
                    activity_type="admin_offer_status_changed",
                    product=offer.product,
                    merchant=offer.merchant,
                    metadata={"offer_id": offer.id, "is_active": offer.is_active},
                )
                messages.success(request, "Offer status updated.")
            elif action == "expire_request":
                request_record = PriceMatchRequest.objects.select_related("product", "merchant", "user").filter(
                    id=request.POST.get("request_id")
                ).first()
                if not request_record:
                    raise ValidationError("Selected price-match request could not be found.")
                request_record.status = "expired"
                request_record.expires_at = timezone.now()
                request_record.save(update_fields=["status", "expires_at", "updated_at"])
                Notification.objects.create(
                    user=request_record.user,
                    title="Deal request closed by admin",
                    message=f"Your deal request for {request_record.product.name} was closed by the admin team.",
                    notification_type="price_match",
                )
                UserActivity.objects.create(
                    user=request.user,
                    activity_type="admin_price_match_closed",
                    product=request_record.product,
                    merchant=request_record.merchant,
                    metadata={"request_id": request_record.id},
                )
                messages.success(request, "Price-match request expired.")
            else:
                messages.error(request, "Unsupported deal action.")
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))

        return redirect("admin_deals")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filters = {
            "q": self.request.GET.get("q", "").strip(),
            "request_status": self.request.GET.get("request_status", "all").strip(),
            "offer_status": self.request.GET.get("offer_status", "all").strip(),
        }

        requests_qs = PriceMatchRequest.objects.select_related("user", "merchant", "product").order_by("-created_at")
        offers_qs = Offer.objects.select_related("product", "merchant").order_by("-updated_at", "price")

        if filters["q"]:
            requests_qs = requests_qs.filter(
                Q(user__email__icontains=filters["q"])
                | Q(product__name__icontains=filters["q"])
                | Q(merchant__shop_name__icontains=filters["q"])
            )
            offers_qs = offers_qs.filter(
                Q(product__name__icontains=filters["q"]) | Q(merchant__shop_name__icontains=filters["q"])
            )
        if filters["request_status"] != "all":
            requests_qs = requests_qs.filter(status=filters["request_status"])
        if filters["offer_status"] == "active":
            offers_qs = offers_qs.filter(is_active=True)
        elif filters["offer_status"] == "inactive":
            offers_qs = offers_qs.filter(is_active=False)

        context.update(
            {
                "deal_filters": filters,
                "price_match_requests": list(requests_qs[:30]),
                "offer_rows": list(offers_qs[:30]),
                "deal_summary": {
                    "active_offers": Offer.objects.filter(is_active=True).count(),
                    "inactive_offers": Offer.objects.filter(is_active=False).count(),
                    "pending_requests": PriceMatchRequest.objects.filter(status="pending").count(),
                    "approved_requests": PriceMatchRequest.objects.filter(status="approved").count(),
                    "expired_requests": PriceMatchRequest.objects.filter(status="expired").count(),
                },
            }
        )
        return context


class AdminDataPageView(StaffRequiredMixin, AdminDashboardShellContextMixin, BaseSiteView):
    template_name = "admin_panel/data.html"
    admin_section = "data"
    admin_title = "Data & Dataset Management"
    admin_intro = "Inspect the real dataset files currently in the workspace and force a catalog reload when you need the DB refreshed."

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "").strip()
        if action == "reload_catalog":
            try:
                summary = CatalogBootstrapService.ensure_loaded(force=True)
                UserActivity.objects.create(
                    user=request.user,
                    activity_type="admin_catalog_reload",
                    metadata=summary,
                )
                messages.success(request, "Catalog reload completed from the dataset folder.")
                self._reload_summary = summary
            except Exception as exc:
                logger.error("Catalog reload failed: %s", exc)
                messages.error(request, "Catalog reload failed.")
        else:
            messages.error(request, "Unsupported data action.")
        return self.render_to_response(self.get_context_data())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data_paths = (getattr(settings, "AI_SETTINGS", {}) or {}).get("DATASET_PATHS", {})
        context.update(
            {
                "dataset_entries": _dataset_directory_entries(),
                "tracked_dataset_paths": data_paths,
                "catalog_summary": {
                    "products": Product.objects.count(),
                    "offers": Offer.objects.filter(is_active=True).count(),
                    "merchants": Merchant.objects.count(),
                    "price_history_records": Product.objects.filter(price_history__isnull=False).distinct().count(),
                },
                "reload_summary": getattr(self, "_reload_summary", None),
            }
        )
        return context


class AdminMLPageView(StaffRequiredMixin, AdminDashboardShellContextMixin, BaseSiteView):
    template_name = "admin_panel/ml.html"
    admin_section = "ml"
    admin_title = "ML Model Control"
    admin_intro = "Adjust the live weighted scoring inputs for price, distance, rating, delivery, and merchant reliability."

    def post(self, request, *args, **kwargs):
        try:
            weights = {}
            for key in ["price", "distance", "rating", "delivery", "reliability"]:
                raw_value = request.POST.get(key, "").strip()
                if raw_value == "":
                    raise ValidationError(f"{key.title()} weight is required.")
                value = float(raw_value)
                if value < 0:
                    raise ValidationError(f"{key.title()} weight cannot be negative.")
                weights[key] = value

            normalized = save_ml_weights(weights)
            UserActivity.objects.create(
                user=request.user,
                activity_type="admin_ml_weights_updated",
                metadata={"weights": normalized},
            )
            messages.success(request, "ML weights updated. Values were normalized and saved for the ranking engine.")
        except (ValidationError, ValueError) as exc:
            messages.error(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
        return redirect("admin_ml")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ml_meta = get_ml_weights_metadata()
        weights = ml_meta["weights"]
        context.update(
            {
                "ml_meta": ml_meta,
                "ml_weights": weights,
                "weight_total": round(sum(weights.values()), 4),
            }
        )
        return context


class AdminNotificationsPageView(StaffRequiredMixin, AdminDashboardShellContextMixin, BaseSiteView):
    template_name = "admin_panel/notifications.html"
    admin_section = "notifications"
    admin_title = "Notification Control"
    admin_intro = "Review admin alerts, monitor system notifications, and trigger a global notice to users or merchants."

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "").strip()
        if action == "mark_all_read":
            request.user.notifications.filter(is_read=False).update(is_read=True)
            messages.success(request, "All admin notifications marked as read.")
        elif action == "mark_read":
            notification = request.user.notifications.filter(id=request.POST.get("notification_id")).first()
            if notification:
                notification.is_read = True
                notification.save(update_fields=["is_read"])
                messages.success(request, "Notification marked as read.")
        elif action == "broadcast":
            title = request.POST.get("title", "").strip()
            message = request.POST.get("message", "").strip()
            target_group = request.POST.get("target_group", "all").strip()
            if not title or not message:
                messages.error(request, "Broadcast title and message are required.")
                return redirect("admin_notifications")

            recipients = User.objects.filter(is_active=True)
            if target_group == "customers":
                recipients = recipients.filter(is_staff=False, is_merchant=False)
            elif target_group == "merchants":
                recipients = recipients.filter(is_merchant=True)
            elif target_group == "admins":
                recipients = recipients.filter(is_staff=True)

            recipient_ids = list(recipients.values_list("id", flat=True))
            Notification.objects.bulk_create(
                [
                    Notification(
                        user_id=user_id,
                        title=title,
                        message=message,
                        notification_type="general",
                    )
                    for user_id in recipient_ids
                ]
            )
            UserActivity.objects.create(
                user=request.user,
                activity_type="admin_notification_broadcast",
                metadata={"target_group": target_group, "recipient_count": len(recipient_ids)},
            )
            messages.success(request, f"Broadcast sent to {len(recipient_ids)} account(s).")
        else:
            messages.error(request, "Unsupported notification action.")
        return redirect("admin_notifications")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filter_value = self.request.GET.get("filter", "all").strip()
        notifications = self.request.user.notifications.all()
        if filter_value == "unread":
            notifications = notifications.filter(is_read=False)
        context.update(
            {
                "admin_notifications": list(notifications.order_by("-created_at")[:50]),
                "notification_filter": filter_value,
                "recent_global_notifications": list(Notification.objects.order_by("-created_at")[:20]),
            }
        )
        return context


class AdminAnalyticsPageView(StaffRequiredMixin, AdminDashboardShellContextMixin, BaseSiteView):
    template_name = "admin_panel/analytics.html"
    admin_section = "analytics"
    admin_title = "Analytics & Reports"
    admin_intro = "Review platform growth, merchant performance, category distribution, and price-match movement using the live database."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        analytics = AdminService.get_analytics()
        dashboard = AdminService.get_dashboard_data()
        context.update(
            {
                "analytics": analytics,
                "dashboard": dashboard,
                "search_activity_count": UserActivity.objects.filter(activity_type__icontains="search").count(),
                "active_user_count": User.objects.filter(is_active=True, is_staff=False).count(),
            }
        )
        return context


class AdminLogsPageView(StaffRequiredMixin, AdminDashboardShellContextMixin, BaseSiteView):
    template_name = "admin_panel/logs.html"
    admin_section = "logs"
    admin_title = "System Logs & Security"
    admin_intro = "Inspect recent admin actions, platform activity, and the local AI engine log file for errors or scraping failures."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        log_path = Path(settings.BASE_DIR) / "logs" / "ai_engine.log"
        context.update(
            {
                "system_health": AdminService.get_system_health(),
                "log_path": str(log_path),
                "log_lines": _recent_log_lines(log_path, limit=60),
                "recent_admin_events": list(
                    UserActivity.objects.select_related("user", "product", "merchant")
                    .filter(Q(activity_type__startswith="admin_") | Q(user__is_staff=True))
                    .order_by("-created_at")[:40]
                ),
                "recent_security_events": list(
                    UserActivity.objects.select_related("user")
                    .filter(Q(activity_type__icontains="login") | Q(activity_type__icontains="password"))
                    .order_by("-created_at")[:25]
                ),
            }
        )
        return context


class AdminProfilePageView(StaffRequiredMixin, AdminDashboardShellContextMixin, BaseSiteView):
    template_name = "admin_panel/profile.html"
    admin_section = "profile"
    admin_title = "Admin Profile & Settings"
    admin_intro = "Update the admin account details, change the password, and keep the control panel credentials strong."

    def _profile_form_values(self):
        if hasattr(self, "_admin_profile_form_values"):
            return self._admin_profile_form_values
        return {
            "first_name": self.request.user.first_name,
            "last_name": self.request.user.last_name,
            "email": self.request.user.email,
            "phone": self.request.user.phone or "",
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["admin_profile_form_values"] = self._profile_form_values()
        return context

    def post(self, request, *args, **kwargs):
        user = request.user
        form_values = {
            "first_name": request.POST.get("first_name", "").strip(),
            "last_name": request.POST.get("last_name", "").strip(),
            "email": request.POST.get("email", "").strip().lower(),
            "phone": request.POST.get("phone", "").strip(),
        }
        self._admin_profile_form_values = form_values

        current_password = request.POST.get("current_password", "")
        new_password = request.POST.get("new_password", "")
        confirm_new_password = request.POST.get("confirm_new_password", "")

        try:
            if not form_values["first_name"] or not form_values["last_name"]:
                raise ValidationError("First name and last name are required.")
            if not form_values["email"]:
                raise ValidationError("Email is required.")
            if User.objects.filter(email__iexact=form_values["email"]).exclude(pk=user.pk).exists():
                raise ValidationError("Another account already uses this email address.")

            normalized_phone = validate_phone_number(form_values["phone"])
            password_change_requested = any([current_password, new_password, confirm_new_password])
            if password_change_requested:
                if not current_password or not new_password or not confirm_new_password:
                    raise ValidationError("Complete all password fields to change the admin password.")
                if not user.check_password(current_password):
                    raise ValidationError("Current password is incorrect.")
                if new_password != confirm_new_password:
                    raise ValidationError("New password and confirmation do not match.")
                validate_strong_password(new_password)

            user.first_name = form_values["first_name"]
            user.last_name = form_values["last_name"]
            user.email = form_values["email"]
            user.phone = normalized_phone
            if password_change_requested:
                user.set_password(new_password)
            user.save()

            if password_change_requested:
                update_session_auth_hash(request, user)

            UserActivity.objects.create(
                user=request.user,
                activity_type="admin_profile_updated",
                metadata={"password_changed": password_change_requested},
            )
            messages.success(request, "Admin profile updated successfully.")
            return redirect("admin_profile")
        except ValidationError as exc:
            messages.error(request, exc.messages[0] if hasattr(exc, "messages") else str(exc))
            return self.render_to_response(self.get_context_data())


def admin_dashboard_legacy_redirect(request):
    return redirect("admin_dashboard")


@method_decorator(never_cache, name="dispatch")
@method_decorator(ensure_csrf_cookie, name="dispatch")
class LoginPageView(BaseSiteView):
    template_name = "auth/login.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(_default_redirect_for_user(request.user))
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        next_url = request.POST.get("next") or request.GET.get("next")

        authenticated_user = _authenticate_from_email_or_username(email, password)

        if not authenticated_user:
            context = self.get_context_data(error="Invalid email or password.")
            return self.render_to_response(context)

        login(request, authenticated_user)
        UserActivity.objects.create(
            user=authenticated_user,
            activity_type="user_login",
            metadata={"login_method": "frontend"},
        )
        if not request.POST.get("remember"):
            request.session.set_expiry(0)

        messages.success(request, "Signed in successfully.")
        if next_url:
            return redirect(next_url)
        return redirect(_default_redirect_for_user(authenticated_user))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next"] = self.request.GET.get("next", "")
        context.setdefault("auth_page_title", "Sign In - DealSphere")
        context.setdefault("auth_heading", "Sign In")
        context.setdefault("auth_copy", "Use the real Django session login for the frontend shell.")
        context.setdefault("auth_submit_label", "Sign In")
        context.setdefault("show_register_link", True)
        context.setdefault("alternate_login_url", reverse("admin_login"))
        context.setdefault("alternate_login_label", "Admin access")
        return context


@method_decorator(never_cache, name="dispatch")
@method_decorator(ensure_csrf_cookie, name="dispatch")
class AdminLoginPageView(BaseSiteView):
    template_name = "auth/login.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(_default_redirect_for_user(request.user))
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        next_url = request.POST.get("next") or request.GET.get("next")

        authenticated_user = _authenticate_from_email_or_username(email, password)
        if not authenticated_user or not authenticated_user.is_staff:
            context = self.get_context_data(error="Invalid admin credentials.")
            return self.render_to_response(context)

        login(request, authenticated_user)
        UserActivity.objects.create(
            user=authenticated_user,
            activity_type="admin_login",
            metadata={"login_method": "admin_frontend"},
        )
        if not request.POST.get("remember"):
            request.session.set_expiry(0)

        messages.success(request, "Admin access granted.")
        if next_url:
            return redirect(next_url)
        return redirect("admin_dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "next": self.request.GET.get("next", ""),
                "admin_mode": True,
                "auth_page_title": "Admin Login - DealSphere",
                "auth_heading": "Admin Access",
                "auth_copy": "Staff accounts only. Successful authentication redirects to the admin control panel.",
                "auth_submit_label": "Admin Login",
                "show_register_link": False,
                "alternate_login_url": reverse("login"),
                "alternate_login_label": "User and merchant login",
            }
        )
        return context


@method_decorator(never_cache, name="dispatch")
@method_decorator(ensure_csrf_cookie, name="dispatch")
class RegisterPageView(BaseSiteView):
    template_name = "auth/register.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(_default_redirect_for_user(request.user))
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["merchant_mode"] = self.request.GET.get("type") == "merchant" or self.request.POST.get("user_type") == "merchant"
        return context

    def post(self, request, *args, **kwargs):
        merchant_mode = request.POST.get("user_type") == "merchant"

        try:
            if merchant_mode:
                create_merchant_account(request.POST, activity_source="frontend")
                messages.success(request, "Merchant registration completed. Please sign in after admin verification.")
            else:
                create_customer_account(request.POST, activity_source="frontend")
                messages.success(request, "Registration completed successfully. Please sign in.")
            return redirect("login")

        except ValidationError as exc:
            context = self.get_context_data(error=str(exc))
            return self.render_to_response(context)

        except OperationalError as exc:
            if "locked" in str(exc).lower():
                context = self.get_context_data(error="The registration system is currently busy. Please wait a moment and try again.")
                return self.render_to_response(context)
            raise


def register_merchant_redirect(request):
    return redirect("/register/?type=merchant")


class ProfilePageView(CustomerRequiredMixin, DashboardShellContextMixin, BaseSiteView):
    template_name = "users/profile.html"
    dashboard_section = "profile"
    dashboard_title = "Profile"
    dashboard_intro = "Manage your user information, password policy, and saved location."

    def _profile_form_values(self):
        if hasattr(self, "_form_values"):
            return self._form_values
        return {
            "first_name": self.request.user.first_name,
            "last_name": self.request.user.last_name,
            "email": self.request.user.email,
            "phone": self.request.user.phone or "",
            "location_lat": self.request.user.location_lat or "",
            "location_lng": self.request.user.location_lng or "",
        }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["profile_form_values"] = self._profile_form_values()
        return context

    def post(self, request, *args, **kwargs):
        user = request.user
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        phone = request.POST.get("phone", "").strip()
        location_lat = request.POST.get("location_lat", "").strip()
        location_lng = request.POST.get("location_lng", "").strip()
        current_password = request.POST.get("current_password", "")
        new_password = request.POST.get("new_password", "")
        confirm_new_password = request.POST.get("confirm_new_password", "")

        self._form_values = {
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "location_lat": location_lat,
            "location_lng": location_lng,
        }

        try:
            if not first_name or not last_name:
                raise ValidationError("First name and last name are required.")
            if not email:
                raise ValidationError("Email is required.")
            if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                raise ValidationError("An account with this email already exists.")

            normalized_phone = validate_phone_number(phone)

            if location_lat or location_lng:
                if not location_lat or not location_lng:
                    raise ValidationError("Both latitude and longitude are required when updating location.")
                validate_location(location_lat, location_lng)
                normalized_lat = Decimal(location_lat)
                normalized_lng = Decimal(location_lng)
            else:
                normalized_lat = None
                normalized_lng = None

            password_change_requested = any([current_password, new_password, confirm_new_password])
            if password_change_requested:
                if not current_password or not new_password or not confirm_new_password:
                    raise ValidationError("Complete all password fields to change your password.")
                if not user.check_password(current_password):
                    raise ValidationError("Current password is incorrect.")
                if new_password != confirm_new_password:
                    raise ValidationError("New password and confirmation do not match.")
                validate_strong_password(new_password)

            user.first_name = first_name
            user.last_name = last_name
            user.email = email
            user.phone = normalized_phone
            user.location_lat = normalized_lat
            user.location_lng = normalized_lng

            if password_change_requested:
                user.set_password(new_password)

            user.save()

            if password_change_requested:
                update_session_auth_hash(request, user)

            messages.success(request, "Profile updated successfully.")
            return redirect("dashboard_profile")

        except ValidationError as exc:
            message = exc.messages[0] if hasattr(exc, "messages") and exc.messages else str(exc)
            messages.error(request, message)
            return self.render_to_response(self.get_context_data())


def logout_redirect(request):
    if request.user.is_authenticated:
        logout(request)
        messages.success(request, "Signed out successfully.")
    return redirect("index")
