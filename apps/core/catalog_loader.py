"""
Catalog bootstrap utilities for loading real CSV datasets into Django models.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import time
from typing import Dict, Optional

import pandas as pd
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import Brand, Category, Merchant, Offer, PriceHistory, Product


User = get_user_model()


def _dataset_path(filename: str) -> Path:
    return Path(settings.BASE_DIR) / "dataset" / filename


def _resolve_flipkart_path() -> Path:
    candidates = [
        _dataset_path("_flipkart_com-ecommerce__.csv"),
        _dataset_path("marketing_sample_for_flipkart_com-ecommerce__20191101_20191130__15k_data.csv"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _read_csv(path: Path) -> pd.DataFrame:
    read_kwargs = {"on_bad_lines": "skip"}
    if getattr(settings, "TESTING", False):
        read_kwargs["nrows"] = 350
    return pd.read_csv(path, **read_kwargs)


def parse_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None

    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None

    cleaned = re.sub(r"[^0-9.\-]", "", text)
    if not cleaned:
        return None

    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def parse_float(value) -> Optional[float]:
    parsed = parse_decimal(value)
    return float(parsed) if parsed is not None else None


def parse_datetime_end_of_day(value):
    if value is None:
        return None

    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None

    try:
        parsed = pd.to_datetime(text)
    except Exception:
        return None

    if pd.isna(parsed):
        return None

    dt = parsed.to_pydatetime()
    return timezone.make_aware(dt.replace(hour=23, minute=59, second=59, microsecond=0))


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def first_image(value) -> Optional[str]:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return None
    url = re.split(r"[|\n;]+", text)[0].strip()

    # Clean Amazon/Flipkart image URLs
    # 1. Handle common malformed suffixes like webp_
    if url.endswith("webp_"):
        url = url[:-5] + "webp"

    # 2. Amazon URLs often have resize parameters like ._SX300_SY300_QL70_FMwebp_.jpg
    # Stripping everything between the last dot before the extension and the extension
    # often yields the original high-resolution image.
    amazon_match = re.search(r"(https://m\.media-amazon\.com/images/.*?[^._]+)(\._.*)(\.jpg|\.png|\.webp)$", url)
    if amazon_match:
        url = amazon_match.group(1) + amazon_match.group(3)

    return url


def extract_primary_category(value) -> Optional[str]:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return None
    return text.split("|")[0].split(">>")[0].strip()


def extract_brand(product_name: str, explicit_brand: Optional[str] = None) -> Optional[str]:
    explicit = str(explicit_brand or "").strip()
    if explicit and explicit.lower() != "nan":
        return explicit

    name = str(product_name or "").strip()
    if not name:
        return None

    first_word = name.split()[0]
    return first_word[:100] if first_word else None


@dataclass
class BootstrapSummary:
    products_created: int = 0
    products_updated: int = 0
    merchants_created: int = 0
    offers_created: int = 0
    price_history_created: int = 0

    def as_dict(self) -> Dict[str, int]:
        return {
            "products_created": self.products_created,
            "products_updated": self.products_updated,
            "merchants_created": self.merchants_created,
            "offers_created": self.offers_created,
            "price_history_created": self.price_history_created,
        }


class CatalogBootstrapService:
    """
    Loads the catalog from the three real CSV datasets already present in the repo.
    """

    DEFAULT_LOCAL_DELIVERY_HOURS = 6
    _ready_state: Optional[bool] = None
    _ready_state_checked_at: float = 0.0

    def __init__(self):
        self.summary = BootstrapSummary()
        self.category_cache: Dict[str, Category] = {}
        self.brand_cache: Dict[str, Brand] = {}
        self.product_cache: Dict[str, Product] = {}
        self.merchant_cache: Dict[str, Merchant] = {}
        self.offer_cache = set(Offer.objects.values_list("product_id", "merchant_id"))

    @classmethod
    def _readiness_cache_seconds(cls) -> int:
        return max(int(getattr(settings, "CATALOG_BOOTSTRAP_READY_CACHE_SECONDS", 300) or 300), 1)

    @classmethod
    def invalidate_readiness_cache(cls):
        cls._ready_state = None
        cls._ready_state_checked_at = 0.0

    @classmethod
    def _validation_thresholds(cls) -> Dict[str, int]:
        validation = (getattr(settings, "AI_SETTINGS", {}) or {}).get("DATASET_VALIDATION", {})
        if getattr(settings, "TESTING", False):
            return {
                "min_products": 200,
                "min_offers": 120,
                "min_merchants": 25,
            }
        return {
            "min_products": int(validation.get("min_products", 1000)),
            "min_offers": int(validation.get("min_offers", 500)),
            "min_merchants": int(validation.get("min_merchants", 50)),
        }

    @classmethod
    def _catalog_is_ready(cls, force_refresh: bool = False) -> bool:
        now = time.monotonic()
        if (
            not force_refresh
            and cls._ready_state is not None
            and now - cls._ready_state_checked_at < cls._readiness_cache_seconds()
        ):
            return bool(cls._ready_state)

        thresholds = cls._validation_thresholds()
        searchable_products = Product.objects.filter(
            Q(amazon_price__isnull=False)
            | Q(flipkart_price__isnull=False)
            | Q(myntra_price__isnull=False)
            | Q(offers__is_active=True)
        ).distinct().count()
        active_offers = Offer.objects.filter(is_active=True).count()
        verified_merchants = Merchant.objects.filter(verified=True).count()
        ready = (
            searchable_products >= thresholds["min_products"]
            and active_offers >= thresholds["min_offers"]
            and verified_merchants >= thresholds["min_merchants"]
            and PriceHistory.objects.exists()
        )
        cls._ready_state = ready
        cls._ready_state_checked_at = now
        return ready

    @classmethod
    def ensure_loaded(cls, force: bool = False) -> Dict[str, int]:
        if not force and cls._catalog_is_ready():
            return {
                "products_created": 0,
                "products_updated": 0,
                "merchants_created": 0,
                "offers_created": 0,
                "price_history_created": 0,
            }

        loader = cls()
        loader.load()
        cls._ready_state = True
        cls._ready_state_checked_at = time.monotonic()
        return loader.summary.as_dict()

    @transaction.atomic
    def load(self):
        self._prime_caches()
        self._load_amazon()
        self._load_flipkart()
        self._load_myntra()
        self._load_local_offers()

    def _prime_caches(self):
        for category in Category.objects.all():
            self.category_cache[category.name.lower()] = category

        for brand in Brand.objects.all():
            self.brand_cache[brand.name.lower()] = brand

        for product in Product.objects.select_related("category", "brand"):
            self.product_cache[normalize_name(product.name)] = product

        for merchant in Merchant.objects.select_related("user"):
            key = normalize_name(f"{merchant.shop_name}|{merchant.address or ''}")
            self.merchant_cache[key] = merchant

    def _get_category(self, name: Optional[str]) -> Optional[Category]:
        if not name:
            return None

        key = name.strip().lower()
        category = self.category_cache.get(key)
        if category:
            return category

        category = Category.objects.create(name=name.strip(), level=0)
        self.category_cache[key] = category
        return category

    def _get_brand(self, name: Optional[str]) -> Optional[Brand]:
        if not name:
            return None

        key = name.strip().lower()
        brand = self.brand_cache.get(key)
        if brand:
            return brand

        brand = Brand.objects.create(name=name.strip())
        self.brand_cache[key] = brand
        return brand

    def _get_or_create_product(
        self,
        *,
        name: str,
        category_name: Optional[str],
        brand_name: Optional[str],
        description: Optional[str] = None,
        image_url: Optional[str] = None,
        amazon_url: Optional[str] = None,
        amazon_price: Optional[Decimal] = None,
        amazon_rating: Optional[float] = None,
        flipkart_url: Optional[str] = None,
        flipkart_price: Optional[Decimal] = None,
        flipkart_rating: Optional[float] = None,
        myntra_url: Optional[str] = None,
        myntra_price: Optional[Decimal] = None,
        myntra_rating: Optional[float] = None,
    ) -> Product:
        key = normalize_name(name)
        product = self.product_cache.get(key)
        category = self._get_category(category_name)
        brand = self._get_brand(brand_name)

        if not product:
            product = Product.objects.create(
                name=name,
                category=category,
                brand=brand,
                description=description,
                image_url=image_url,
                amazon_url=amazon_url,
                amazon_price=amazon_price,
                amazon_rating=amazon_rating,
                flipkart_url=flipkart_url,
                flipkart_price=flipkart_price,
                flipkart_rating=flipkart_rating,
                myntra_url=myntra_url,
                myntra_price=myntra_price,
                myntra_rating=myntra_rating,
            )
            self.product_cache[key] = product
            self.summary.products_created += 1
            return product

        updated = False
        if category and product.category_id is None:
            product.category = category
            updated = True
        if brand and product.brand_id is None:
            product.brand = brand
            updated = True
        if description and not product.description:
            product.description = description
            updated = True
        if image_url and not product.image_url:
            product.image_url = image_url
            updated = True
        if amazon_url and not product.amazon_url:
            product.amazon_url = amazon_url
            updated = True
        if amazon_price is not None and product.amazon_price is None:
            product.amazon_price = amazon_price
            updated = True
        if amazon_rating is not None and product.amazon_rating is None:
            product.amazon_rating = amazon_rating
            updated = True
        if flipkart_url and not product.flipkart_url:
            product.flipkart_url = flipkart_url
            updated = True
        if flipkart_price is not None and product.flipkart_price is None:
            product.flipkart_price = flipkart_price
            updated = True
        if flipkart_rating is not None and product.flipkart_rating is None:
            product.flipkart_rating = flipkart_rating
            updated = True
        if myntra_url and not product.myntra_url:
            product.myntra_url = myntra_url
            updated = True
        if myntra_price is not None and product.myntra_price is None:
            product.myntra_price = myntra_price
            updated = True
        if myntra_rating is not None and product.myntra_rating is None:
            product.myntra_rating = myntra_rating
            updated = True

        if updated:
            product.save()
            self.summary.products_updated += 1

        return product

    def _ensure_price_history(self, product: Product, source: str, price: Optional[Decimal], merchant: Optional[Merchant] = None):
        if price is None:
            return

        exists = PriceHistory.objects.filter(product=product, source=source, price=price, merchant=merchant).exists()
        if exists:
            return

        PriceHistory.objects.create(product=product, source=source, price=price, merchant=merchant)
        self.summary.price_history_created += 1

    def _load_amazon(self):
        path = _dataset_path("amazon.csv")
        if not path.exists():
            return

        df = _read_csv(path)
        for row in df.itertuples(index=False):
            name = str(getattr(row, "product_name", "")).strip()
            if not name:
                continue

            price = parse_decimal(getattr(row, "discounted_price", None))
            rating = parse_float(getattr(row, "rating", None))
            product = self._get_or_create_product(
                name=name,
                category_name=extract_primary_category(getattr(row, "category", None)),
                brand_name=extract_brand(name),
                description=str(getattr(row, "about_product", "")).strip() or None,
                image_url=first_image(getattr(row, "img_link", None)),
                amazon_url=str(getattr(row, "product_link", "")).strip() or None,
                amazon_price=price,
                amazon_rating=rating,
            )
            self._ensure_price_history(product, "amazon", price)

    def _load_flipkart(self):
        path = _resolve_flipkart_path()
        if not path.exists():
            return

        df = _read_csv(path)
        for row in df.itertuples(index=False):
            name = str(getattr(row, "Product_Title", getattr(row, "Product Title", ""))).strip()
            if not name:
                name = str(getattr(row, "Product_Title", "")).strip()
            if not name:
                continue

            price = parse_decimal(getattr(row, "Price", None))
            product = self._get_or_create_product(
                name=name,
                category_name=extract_primary_category(getattr(row, "Bb_Category", getattr(row, "Bb Category", None))),
                brand_name=extract_brand(name, getattr(row, "Brand", None)),
                description=str(getattr(row, "Product_Description", getattr(row, "Product Description", ""))).strip() or None,
                image_url=first_image(getattr(row, "Image_Url", getattr(row, "Image Url", None))),
                flipkart_url=str(getattr(row, "Url", "")).strip() or None,
                flipkart_price=price,
            )
            self._ensure_price_history(product, "flipkart", price)

    def _load_myntra(self):
        path = _dataset_path("myntra202305041052.csv")
        if not path.exists():
            return

        df = _read_csv(path)
        for row in df.itertuples(index=False):
            name = str(getattr(row, "name", "")).strip()
            if not name:
                continue

            price = parse_decimal(getattr(row, "price", None))
            rating = parse_float(getattr(row, "rating", None))
            product = self._get_or_create_product(
                name=name,
                category_name=None,
                brand_name=extract_brand(name, getattr(row, "seller", None)),
                image_url=first_image(getattr(row, "img", None)),
                myntra_url=str(getattr(row, "purl", "")).strip() or None,
                myntra_price=price,
                myntra_rating=rating,
            )
            self._ensure_price_history(product, "myntra", price)

    def _build_merchant_username(self, shop_name: str, city: str) -> str:
        base = slugify(f"{shop_name}-{city}") or "merchant"
        username = f"merchant-{base}"[:140]
        candidate = username
        suffix = 1
        while User.objects.filter(username=candidate).exists():
            suffix += 1
            candidate = f"{username[:130]}-{suffix}"
        return candidate

    def _get_or_create_merchant(self, shop_name: str, city: str) -> Merchant:
        key = normalize_name(f"{shop_name}|{city}")
        merchant = self.merchant_cache.get(key)
        if merchant:
            return merchant

        username = self._build_merchant_username(shop_name, city)
        email = f"{username}@dealsphere.local"
        user = User.objects.create(
            username=username,
            email=email,
            is_merchant=True,
            is_verified=True,
            is_active=True,
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])

        merchant = Merchant.objects.create(
            user=user,
            shop_name=shop_name,
            address=city,
            verified=True,
            delivery_radius_km=10,
        )
        self.merchant_cache[key] = merchant
        self.summary.merchants_created += 1
        return merchant

    def _load_local_offers(self):
        path = _dataset_path("local_store_offer_dataset.csv")
        if not path.exists():
            return

        df = _read_csv(path)
        for row in df.itertuples(index=False):
            shop_name = str(getattr(row, "store_name", "")).strip()
            city = str(getattr(row, "city", "")).strip()
            product_name = str(getattr(row, "product_name", "")).strip()
            if not shop_name or not product_name:
                continue

            merchant = self._get_or_create_merchant(shop_name, city)
            price = parse_decimal(getattr(row, "offer_price_inr", None))
            original_price = parse_decimal(getattr(row, "original_price_inr", None))
            valid_until = parse_datetime_end_of_day(getattr(row, "offer_end_date", None))
            product = self._get_or_create_product(
                name=product_name,
                category_name=extract_primary_category(getattr(row, "product_category", None)),
                brand_name=extract_brand(product_name, getattr(row, "brand", None)),
            )

            offer_key = (product.id, merchant.id)
            if offer_key not in self.offer_cache:
                Offer.objects.create(
                    product=product,
                    merchant=merchant,
                    price=price or Decimal("0.01"),
                    original_price=original_price,
                    delivery_time_hours=self.DEFAULT_LOCAL_DELIVERY_HOURS,
                    stock_quantity=1,
                    is_active=(valid_until is None or valid_until >= timezone.now()),
                    valid_until=valid_until,
                )
                self.offer_cache.add(offer_key)
                self.summary.offers_created += 1

            self._ensure_price_history(product, "local", price, merchant=merchant)
