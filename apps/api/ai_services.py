"""
Real-data-backed AI helper services for API endpoints.
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from statistics import mean
from typing import Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from django.conf import settings
from django.db.models import Avg, Count, Min, Max, Q
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.core.catalog_loader import CatalogBootstrapService
from apps.core.models import Offer, PriceHistory, Product
from apps.core.runtime_config import get_ml_weights
from apps.users.services import SearchService


def _ensure_catalog_loaded():
    CatalogBootstrapService.ensure_loaded()


def _product_price_candidates(product: Product) -> List[Dict]:
    candidates = []

    if product.amazon_price is not None:
        candidates.append(
            {
                "source": "amazon",
                "merchant": "Amazon",
                "price": float(product.amazon_price),
                "delivery_time": 24.0,
                "distance": None,
                "rating": float(product.amazon_rating or 0),
                "reliability": 0.9,
            }
        )

    if product.flipkart_price is not None:
        candidates.append(
            {
                "source": "flipkart",
                "merchant": "Flipkart",
                "price": float(product.flipkart_price),
                "delivery_time": 48.0,
                "distance": None,
                "rating": float(product.flipkart_rating or 0),
                "reliability": 0.85,
            }
        )

    if product.myntra_price is not None:
        candidates.append(
            {
                "source": "myntra",
                "merchant": "Myntra",
                "price": float(product.myntra_price),
                "delivery_time": 36.0,
                "distance": None,
                "rating": float(product.myntra_rating or 0),
                "reliability": 0.84,
            }
        )

    for offer in product.offers.filter(is_active=True).select_related("merchant").order_by("price"):
        candidates.append(
            {
                "source": "local",
                "merchant": offer.merchant.shop_name,
                "merchant_id": offer.merchant_id,
                "price": float(offer.price),
                "delivery_time": float(offer.delivery_time_hours),
                "distance": None,
                "rating": float(offer.merchant.rating or 0),
                "reliability": 1.0 if offer.merchant.verified else 0.7,
            }
        )

    return candidates


def _basket_optimization_from_entries(entries: List[Dict[str, object]], budget: Optional[float] = None) -> Dict:
    best_split_items = []
    baseline_items = []
    stores = defaultdict(list)
    total_best_cost = 0.0
    total_baseline_cost = 0.0

    for entry in entries:
        product = entry.get("product")
        if not product:
            continue

        try:
            quantity = int(entry.get("quantity") or 0)
        except (TypeError, ValueError):
            quantity = 0
        if quantity < 1:
            continue

        candidates = _product_price_candidates(product)
        if not candidates:
            continue

        best_candidate = min(candidates, key=lambda item: item["price"])
        online_candidates = [candidate for candidate in candidates if candidate["source"] in {"amazon", "flipkart", "myntra"}]
        baseline_candidate = min(online_candidates, key=lambda item: item["price"]) if online_candidates else best_candidate

        best_line = {
            "product_id": product.id,
            "product_name": product.name,
            "quantity": quantity,
            "source": best_candidate["source"],
            "merchant": best_candidate["merchant"],
            "merchant_id": best_candidate.get("merchant_id"),
            "unit_price": best_candidate["price"],
            "line_total": round(best_candidate["price"] * quantity, 2),
        }
        baseline_line = {
            "product_id": product.id,
            "product_name": product.name,
            "quantity": quantity,
            "source": baseline_candidate["source"],
            "merchant": baseline_candidate["merchant"],
            "merchant_id": baseline_candidate.get("merchant_id"),
            "unit_price": baseline_candidate["price"],
            "line_total": round(baseline_candidate["price"] * quantity, 2),
        }

        best_split_items.append(best_line)
        baseline_items.append(baseline_line)
        total_best_cost += best_line["line_total"]
        total_baseline_cost += baseline_line["line_total"]
        stores[best_candidate["merchant"]].append(best_line)

    savings = round(total_baseline_cost - total_best_cost, 2)

    best_option = {
        "strategy": "split_purchase",
        "total_cost": round(total_best_cost, 2),
        "stores": list(stores.keys()),
        "products_by_store": dict(stores),
        "savings": savings if savings > 0 else 0,
        "delivery_cost": 0.0,
        "time_cost": 0.0,
        "items": best_split_items,
    }

    baseline_option = {
        "strategy": "online_only_baseline",
        "total_cost": round(total_baseline_cost, 2),
        "stores": sorted({item["merchant"] for item in baseline_items}),
        "products_by_store": {},
        "savings": 0.0,
        "delivery_cost": 0.0,
        "time_cost": 0.0,
        "items": baseline_items,
    }

    recommendations = []
    if best_split_items:
        recommendations.append(f"Best split-purchase total: Rs.{best_option['total_cost']:.2f}")
        if savings > 0:
            recommendations.append(f"Estimated savings over online-only baseline: Rs.{savings:.2f}")
        recommendations.append(f"Use {len(best_option['stores'])} source(s): {', '.join(best_option['stores'])}")

    within_budget = None if budget is None else best_option["total_cost"] <= float(budget)

    return {
        "best_option": best_option if best_split_items else None,
        "all_options": [best_option, baseline_option] if best_split_items else [],
        "baseline_cost": round(total_baseline_cost, 2),
        "max_savings": savings if savings > 0 else 0,
        "product_count": len(best_split_items),
        "budget": float(budget) if budget is not None else None,
        "within_budget": within_budget,
        "recommendations": recommendations,
    }


def _barcode_match(row_code: str, barcode: str) -> bool:
    row_values = {str(row_code or "").strip()}
    barcode_values = {str(barcode or "").strip()}
    if "" in row_values or "" in barcode_values:
        return False

    stripped_row = next(iter(row_values)).lstrip("0")
    stripped_barcode = next(iter(barcode_values)).lstrip("0")
    if stripped_row:
        row_values.add(stripped_row)
    if stripped_barcode:
        barcode_values.add(stripped_barcode)
    return bool(row_values & barcode_values)


def _external_barcode_sources():
    base_dir = Path(__file__).resolve().parents[2]
    return [
        (
            "openproductsfacts",
            [
                base_dir / "dataset" / "en.openproductsfacts.org.products.csv",
                base_dir / "dataset" / "en.openproductsfacts.org.products.csv" / "en.openproductsfacts.org.products.csv",
            ],
        ),
        (
            "openfoodfacts",
            [
                base_dir / "dataset" / "en.openfoodfacts.org.products.csv",
                base_dir / "dataset" / "en.openfoodfacts.org.products.csv" / "en.openfoodfacts.org.products.csv",
            ],
        ),
    ]


def _lookup_external_barcode(barcode: str) -> Optional[Dict]:
    for source_name, candidate_paths in _external_barcode_sources():
        for path in candidate_paths:
            if not path.exists() or not path.is_file():
                continue

            with path.open("r", encoding="utf-8", errors="ignore", newline="") as csv_file:
                reader = csv.DictReader(csv_file, delimiter="\t")
                for row in reader:
                    if not _barcode_match(row.get("code", ""), barcode):
                        continue

                    product_name = (row.get("product_name") or "").strip()
                    if not product_name:
                        continue

                    category = (row.get("main_category_en") or row.get("categories_en") or "").strip() or None
                    brand = (row.get("brands") or "").strip() or None
                    image_url = (row.get("image_url") or row.get("image_small_url") or "").strip() or None

                    similar_products = list(
                        Product.objects.filter(name__icontains=product_name[:40]).values("id", "name", "image_url")[:5]
                    )

                    return {
                        "found": True,
                        "barcode": barcode,
                        "match_type": "external_dataset",
                        "product": {
                            "id": None,
                            "name": product_name,
                            "image_url": image_url,
                            "category": category,
                            "brand": brand,
                            "source_dataset": source_name,
                        },
                        "confidence": 1.0,
                        "similar_products": similar_products,
                        "price_comparison": [],
                    }
    return None


def _visual_dataset_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "dataset" / "retail_product_checkout"


def _coarse_visual_bucket(value: int) -> int:
    return min(15, max(0, value // 16))


def _image_fingerprint(image_source) -> Optional[List[float]]:
    try:
        with Image.open(image_source) as raw_image:
            image = ImageOps.exif_transpose(raw_image).convert("RGB")
            original_width, original_height = image.size
            image = image.resize((64, 64))
            histogram = image.histogram()
    except (FileNotFoundError, UnidentifiedImageError, OSError):
        return None

    buckets = [0.0] * 48
    for channel_index in range(3):
        channel_start = channel_index * 256
        for value, count in enumerate(histogram[channel_start : channel_start + 256]):
            bucket_index = _coarse_visual_bucket(value)
            buckets[(channel_index * 16) + bucket_index] += float(count)

    total = sum(buckets) or 1.0
    normalized = [round(bucket / total, 6) for bucket in buckets]

    aspect_ratio = original_width / max(original_height, 1)
    normalized.append(round(min(aspect_ratio, 4.0) / 4.0, 6))
    return normalized


def _visual_similarity(left: List[float], right: List[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    distance = sum(abs(a - b) for a, b in zip(left, right))
    return round(max(0.0, 1.0 - (distance / 2.5)), 4)


def _visual_supercategory_to_catalog(supercategory: str) -> Dict[str, Optional[str]]:
    normalized = str(supercategory or "").strip().lower().replace("_", " ")
    grocery_groups = {
        "puffed food",
        "dried fruit",
        "dried food",
        "instant drink",
        "instant noodles",
        "dessert",
        "drink",
        "alcohol",
        "milk",
        "canned food",
        "chocolate",
        "gum",
        "candy",
        "seasoner",
    }
    if normalized in grocery_groups:
        return {"query": "grocery", "category": "Grocery"}
    if normalized == "personal hygiene":
        return {"query": "personal care", "category": "Health & Personal Care"}
    if normalized == "tissue":
        return {"query": "tissue", "category": "Home & Kitchen"}
    if normalized == "stationery":
        return {"query": "stationery", "category": "Stationery"}
    return {"query": normalized, "category": None}


AMAZON_ASIN_PATTERN = re.compile(r"/(?:dp|gp/product|gp/aw/d|product-reviews)/([A-Z0-9]{10})(?:[/?]|$)", re.IGNORECASE)
AMAZON_DOMAIN_COUNTRY_MAP = {
    "amazon.in": "IN",
    "amazon.com": "US",
    "amazon.co.uk": "UK",
    "amazon.ca": "CA",
    "amazon.com.au": "AU",
    "amazon.ae": "AE",
    "amazon.de": "DE",
    "amazon.fr": "FR",
    "amazon.it": "IT",
    "amazon.es": "ES",
    "amazon.sg": "SG",
    "amazon.nl": "NL",
    "amazon.se": "SE",
    "amazon.pl": "PL",
    "amazon.com.tr": "TR",
    "amazon.com.mx": "MX",
    "amazon.com.br": "BR",
    "amazon.sa": "SA",
    "amazon.eg": "EG",
    "amazon.co.jp": "JP",
}
AMAZON_HOST_DOMAIN_CODE_MAP = {
    "amazon.in": "in",
    "amazon.com": "com",
    "amazon.co.uk": "co.uk",
    "amazon.ca": "ca",
    "amazon.com.au": "com.au",
    "amazon.ae": "ae",
    "amazon.de": "de",
    "amazon.fr": "fr",
    "amazon.it": "it",
    "amazon.es": "es",
    "amazon.sg": "sg",
    "amazon.nl": "nl",
    "amazon.se": "se",
    "amazon.pl": "pl",
    "amazon.com.tr": "com.tr",
    "amazon.com.mx": "com.mx",
    "amazon.com.br": "com.br",
    "amazon.sa": "sa",
    "amazon.eg": "eg",
    "amazon.co.jp": "co.jp",
}


def _amazon_review_api_config() -> Dict[str, object]:
    config = getattr(settings, "AMAZON_REVIEW_API_SETTINGS", {}) or {}
    timeout = int(config.get("timeout_seconds", 12) or 12)
    return {
        "endpoint": str(config.get("endpoint", "")).strip(),
        "host": str(config.get("host", "")).strip(),
        "key": str(config.get("key", "")).strip(),
        "default_country": str(config.get("default_country", "IN")).strip().upper() or "IN",
        "timeout_seconds": max(timeout, 1),
        "enabled": bool(config.get("enabled")),
    }


def _amazon_product_info_api_config() -> Dict[str, object]:
    config = getattr(settings, "AMAZON_PRODUCT_INFO_API_SETTINGS", {}) or {}
    timeout = int(config.get("timeout_seconds", 12) or 12)
    return {
        "endpoint": str(config.get("endpoint", "")).strip(),
        "host": str(config.get("host", "")).strip(),
        "key": str(config.get("key", "")).strip(),
        "default_domain": str(config.get("default_domain", "in")).strip().lower() or "in",
        "timeout_seconds": max(timeout, 1),
        "enabled": bool(config.get("enabled")),
    }


def _extract_amazon_asin(url: Optional[str]) -> Optional[str]:
    normalized_url = str(url or "").strip()
    if not normalized_url:
        return None

    match = AMAZON_ASIN_PATTERN.search(normalized_url)
    if match:
        return match.group(1).upper()

    parsed = urlparse(normalized_url)
    query_values = {}
    if parsed.query:
        query_values = dict(item.split("=", 1) for item in parsed.query.split("&") if "=" in item)
    asin = query_values.get("asin") or query_values.get("ASIN")
    if asin and len(asin) >= 10:
        return asin[:10].upper()

    return None


def _amazon_country_from_url(url: Optional[str], default_country: str = "IN") -> str:
    host = urlparse(str(url or "")).netloc.lower().strip()
    for domain, country_code in sorted(AMAZON_DOMAIN_COUNTRY_MAP.items(), key=lambda item: len(item[0]), reverse=True):
        if host.endswith(domain):
            return country_code
    return default_country


def _amazon_domain_from_url(url: Optional[str], default_domain: str = "in") -> str:
    host = urlparse(str(url or "")).netloc.lower().strip()
    for domain, domain_code in sorted(AMAZON_HOST_DOMAIN_CODE_MAP.items(), key=lambda item: len(item[0]), reverse=True):
        if host.endswith(domain):
            return domain_code
    return default_domain


def _normalize_amazon_rating_distribution(distribution: Optional[Dict]) -> Dict[str, int]:
    if not isinstance(distribution, dict):
        return {}
    normalized = {}
    for key, value in distribution.items():
        try:
            normalized[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return normalized


def _normalize_amazon_reviews(reviews: Optional[List[Dict]], limit: int) -> List[Dict]:
    normalized_reviews = []
    for review in list(reviews or [])[:limit]:
        try:
            star_rating = float(review.get("review_star_rating")) if review.get("review_star_rating") not in (None, "") else None
        except (TypeError, ValueError):
            star_rating = None

        normalized_reviews.append(
            {
                "review_id": review.get("review_id"),
                "review_title": str(review.get("review_title") or "").strip(),
                "review_comment": str(review.get("review_comment") or "").strip(),
                "review_star_rating": star_rating,
                "review_link": review.get("review_link"),
                "review_author": str(review.get("review_author") or "").strip(),
                "review_author_avatar": review.get("review_author_avatar"),
                "review_date": str(review.get("review_date") or "").strip(),
                "is_verified_purchase": bool(review.get("is_verified_purchase")),
                "helpful_vote_statement": str(review.get("helpful_vote_statement") or "").strip(),
                "review_images": [image for image in list(review.get("review_images") or []) if image],
            }
        )
    return normalized_reviews


def _extract_first_non_empty(mapping: Optional[Dict], *keys):
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _extract_numeric_price(value) -> Optional[float]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    cleaned = re.sub(r"[^0-9.,-]", "", str(value))
    if not cleaned:
        return None
    if cleaned.count(",") and cleaned.count("."):
        cleaned = cleaned.replace(",", "")
    elif cleaned.count(",") and not cleaned.count("."):
        cleaned = cleaned.replace(",", ".")
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return None


def _normalize_feature_list(value) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, dict):
        return [f"{key}: {str(item).strip()}" for key, item in value.items() if str(item).strip()]
    if value in (None, ""):
        return []
    return [str(value).strip()]


class DatasetVisualSearchService:
    """Lightweight, real image-similarity lookup against the local RPC retail dataset."""

    MAX_REFERENCE_IMAGES_PER_CATEGORY = 8

    @classmethod
    @lru_cache(maxsize=1)
    def dataset_index(cls) -> Dict[str, object]:
        dataset_dir = _visual_dataset_dir()
        annotation_specs = (
            ("instances_val2019.json", "val2019"),
            ("instances_train2019.json", "train2019"),
        )
        records: List[Dict[str, object]] = []
        seen_per_category: Dict[int, int] = defaultdict(int)
        category_labels: Dict[int, Dict[str, str]] = {}

        for annotation_name, image_subdir in annotation_specs:
            annotation_path = dataset_dir / annotation_name
            if not annotation_path.exists():
                continue

            try:
                payload = json.loads(annotation_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            image_lookup = {image["id"]: image for image in payload.get("images", [])}
            for category in payload.get("categories", []):
                category_labels[int(category["id"])] = {
                    "name": str(category.get("name", "")).strip(),
                    "supercategory": str(category.get("supercategory", "")).strip(),
                }

            for annotation in payload.get("annotations", []):
                category_id = int(annotation.get("category_id", 0) or 0)
                if not category_id or seen_per_category[category_id] >= cls.MAX_REFERENCE_IMAGES_PER_CATEGORY:
                    continue

                category_info = category_labels.get(category_id)
                image_info = image_lookup.get(annotation.get("image_id"))
                if not category_info or not image_info:
                    continue

                file_name = str(image_info.get("file_name", "")).strip()
                if not file_name:
                    continue

                candidate_paths = [
                    dataset_dir / file_name,
                    dataset_dir / image_subdir / file_name,
                    dataset_dir / "val2019" / file_name,
                    dataset_dir / "train2019" / file_name,
                ]
                image_path = next((path for path in candidate_paths if path.exists()), None)
                if not image_path:
                    continue

                fingerprint = _image_fingerprint(image_path)
                if not fingerprint:
                    continue

                records.append(
                    {
                        "category_id": category_id,
                        "category_name": category_info["name"],
                        "supercategory": category_info["supercategory"],
                        "image_path": str(image_path),
                        "file_name": image_path.name,
                        "fingerprint": fingerprint,
                    }
                )
                seen_per_category[category_id] += 1

        return {
            "records": records,
            "category_count": len(category_labels),
            "reference_images": len(records),
        }

    @classmethod
    def identify(cls, image_file) -> Dict[str, object]:
        dataset = cls.dataset_index()
        records = dataset.get("records", [])
        if not records:
            return {
                "status": "unavailable",
                "message": "The retail image dataset is not available in this workspace.",
                "predicted_category": None,
                "predicted_supercategory": None,
                "confidence": 0.0,
                "all_predictions": [],
                "matching_products": [],
            }

        try:
            image_file.seek(0)
        except Exception:
            pass

        fingerprint = _image_fingerprint(image_file)
        if not fingerprint:
            return {
                "status": "invalid_image",
                "message": "The uploaded file could not be processed as an image.",
                "predicted_category": None,
                "predicted_supercategory": None,
                "confidence": 0.0,
                "all_predictions": [],
                "matching_products": [],
            }

        ranked_matches = []
        for record in records:
            similarity = _visual_similarity(fingerprint, record["fingerprint"])
            ranked_matches.append(
                {
                    "category_name": record["category_name"],
                    "supercategory": record["supercategory"],
                    "similarity": similarity,
                    "reference_image": record["file_name"],
                }
            )

        ranked_matches.sort(key=lambda item: item["similarity"], reverse=True)
        top_matches = ranked_matches[:8]

        grouped_predictions: Dict[str, Dict[str, object]] = {}
        for match in top_matches:
            key = f"{match['supercategory']}::{match['category_name']}"
            bucket = grouped_predictions.setdefault(
                key,
                {
                    "predicted_category": match["category_name"],
                    "predicted_supercategory": match["supercategory"],
                    "confidence": 0.0,
                    "supporting_matches": 0,
                },
            )
            bucket["confidence"] = max(bucket["confidence"], match["similarity"])
            bucket["supporting_matches"] += 1

        all_predictions = sorted(
            grouped_predictions.values(),
            key=lambda item: (item["confidence"], item["supporting_matches"]),
            reverse=True,
        )
        best_prediction = all_predictions[0] if all_predictions else None

        matching_products: List[Product] = []
        seen_product_ids = set()
        if best_prediction:
            catalog_target = _visual_supercategory_to_catalog(best_prediction["predicted_supercategory"])
            query_candidates = [
                catalog_target.get("query"),
                best_prediction["predicted_supercategory"].replace("_", " "),
                best_prediction["predicted_category"].replace("_", " "),
            ]
            for query in query_candidates:
                if not query:
                    continue
                for product in SearchService.search_products(
                    query=query,
                    category=catalog_target.get("category"),
                    sort_by="relevance",
                )[:8]:
                    if product.id in seen_product_ids:
                        continue
                    seen_product_ids.add(product.id)
                    matching_products.append(product)
                if matching_products:
                    break

        return {
            "status": "ok" if best_prediction else "no_match",
            "predicted_category": best_prediction["predicted_category"] if best_prediction else None,
            "predicted_supercategory": best_prediction["predicted_supercategory"] if best_prediction else None,
            "confidence": round(float(best_prediction["confidence"]), 4) if best_prediction else 0.0,
            "all_predictions": all_predictions[:5],
            "matching_products": matching_products[:8],
            "reference_matches": top_matches[:5],
            "dataset_reference_images": dataset.get("reference_images", 0),
        }


class RealAIService:
    @staticmethod
    def rank_products(products_data: List[Dict], weights: Optional[Dict[str, float]] = None) -> List[Dict]:
        if not products_data:
            return []

        weights = weights or get_ml_weights()

        valid_products = [product for product in products_data if product.get("price") not in (None, "", 0)]
        if not valid_products:
            return []

        min_price = min(float(product["price"]) for product in valid_products if float(product["price"]) > 0)

        ranked = []
        for product in valid_products:
            price = max(float(product.get("price", 0) or 0), 0.01)
            distance = product.get("distance")
            delivery_time = float(product.get("delivery_time") or product.get("delivery_time_hours") or 24)
            rating = float(product.get("rating") or 0)
            reliability = float(product.get("reliability") or 0)

            price_score = min_price / price
            distance_score = 1 / (1 + float(distance)) if distance is not None else 0.5
            rating_score = rating / 5 if rating else 0
            delivery_score = 1 / (1 + delivery_time / 24)
            reliability_score = reliability if reliability <= 1 else min(reliability / 5, 1)

            ml_score = (
                weights["price"] * price_score
                + weights["distance"] * distance_score
                + weights["rating"] * rating_score
                + weights["delivery"] * delivery_score
                + weights["reliability"] * reliability_score
            ) * 100

            enriched = dict(product)
            enriched["ml_score"] = round(ml_score, 2)
            enriched["feature_scores"] = {
                "price_score": round(price_score, 4),
                "distance_score": round(distance_score, 4),
                "rating_score": round(rating_score, 4),
                "delivery_score": round(delivery_score, 4),
                "reliability_score": round(reliability_score, 4),
            }
            ranked.append(enriched)

        ranked.sort(key=lambda item: item["ml_score"], reverse=True)
        for index, product in enumerate(ranked, start=1):
            product["rank"] = index
        return ranked

    @staticmethod
    def optimize_basket(product_names: List[str], quantities: List[int], budget: Optional[float] = None) -> Dict:
        _ensure_catalog_loaded()
        entries = []
        for product_name, quantity in zip(product_names, quantities):
            product = Product.objects.filter(name__icontains=product_name).prefetch_related("offers__merchant").first()
            if not product:
                continue
            entries.append({"product": product, "quantity": quantity})
        return _basket_optimization_from_entries(entries, budget=budget)

    @staticmethod
    def optimize_cart_items(cart_items, budget: Optional[float] = None) -> Dict:
        _ensure_catalog_loaded()
        entries = [{"product": item.product, "quantity": item.quantity} for item in cart_items if getattr(item, "product", None)]
        return _basket_optimization_from_entries(entries, budget=budget)

    @staticmethod
    def predict_price(product_id: int, days_ahead: int = 7) -> Optional[Dict]:
        _ensure_catalog_loaded()
        product = Product.objects.filter(id=product_id).first()
        if not product:
            return None

        history = list(PriceHistory.objects.filter(product=product).order_by("created_at"))
        current_source_prices = [
            float(price)
            for price in [product.amazon_price, product.flipkart_price, product.myntra_price]
            if price is not None
        ]
        current_source_prices.extend(
            float(offer.price)
            for offer in product.offers.filter(is_active=True).only("price")
            if offer.price is not None
        )
        current_price = round(min(current_source_prices), 2) if current_source_prices else 0.0

        if len(history) < 3:
            related_filters = Q()
            if product.category_id:
                related_filters |= Q(product__category_id=product.category_id)
            if product.brand_id:
                related_filters |= Q(product__brand_id=product.brand_id)
            related_history = PriceHistory.objects.none()
            if related_filters:
                related_history = PriceHistory.objects.filter(related_filters).exclude(product=product).order_by("-created_at")[:120]
            related_prices = [float(item.price) for item in related_history if item.price is not None]

            benchmark_prices = []
            if current_source_prices:
                benchmark_prices.extend(current_source_prices)
            if related_prices:
                benchmark_prices.append(mean(related_prices))

            target_price = round(mean(benchmark_prices), 2) if benchmark_prices else current_price
            step = ((target_price - current_price) / max(days_ahead, 1)) if days_ahead else 0.0
            predictions = [
                round(max(current_price + (step * offset), 0), 2)
                for offset in range(1, days_ahead + 1)
            ]
            dates = [
                (timezone.now().date() + timedelta(days=offset)).isoformat()
                for offset in range(1, days_ahead + 1)
            ]
            best_price = min(predictions) if predictions else current_price
            best_day = dates[predictions.index(best_price)] if predictions else timezone.now().date().isoformat()
            return {
                "status": "heuristic_fallback",
                "product_id": str(product.id),
                "product_name": product.name,
                "current_price": current_price,
                "predictions": predictions,
                "dates": dates,
                "confidence_intervals": [],
                "trend": "down" if target_price < current_price else "up" if target_price > current_price else "flat",
                "best_day_to_buy": {"date": best_day, "predicted_price": best_price},
                "confidence_level": "low",
                "fallback_basis": {
                    "same_product_history_points": len(history),
                    "related_history_points": len(related_prices),
                    "active_price_sources": len(current_source_prices),
                },
                "message": "Forecast uses live marketplace and related-category pricing because this product has limited direct history.",
            }

        prices = [float(item.price) for item in history]
        recent_prices = prices[-min(5, len(prices)):]
        average_step = 0.0
        if len(recent_prices) > 1:
            deltas = [recent_prices[index] - recent_prices[index - 1] for index in range(1, len(recent_prices))]
            average_step = mean(deltas)

        current_price = prices[-1]
        predictions = []
        dates = []
        for offset in range(1, days_ahead + 1):
            predicted_price = round(max(current_price + average_step * offset, 0), 2)
            predictions.append(predicted_price)
            dates.append((timezone.now().date() + timedelta(days=offset)).isoformat())

        best_price = min(predictions) if predictions else current_price
        best_day = dates[predictions.index(best_price)] if predictions else timezone.now().date().isoformat()

        return {
            "status": "ok",
            "product_id": str(product.id),
            "product_name": product.name,
            "current_price": current_price,
            "predictions": predictions,
            "dates": dates,
            "confidence_intervals": [],
            "trend": "down" if average_step < 0 else "up" if average_step > 0 else "flat",
            "best_day_to_buy": {"date": best_day, "predicted_price": best_price},
            "confidence_level": "medium",
        }

    @staticmethod
    def identify_product(image_file) -> Dict:
        _ensure_catalog_loaded()
        return DatasetVisualSearchService.identify(image_file)

    @staticmethod
    def barcode_search(barcode: str) -> Dict:
        _ensure_catalog_loaded()
        product = Product.objects.filter(barcode=barcode).prefetch_related("offers__merchant").first()
        if not product:
            external_match = _lookup_external_barcode(barcode)
            if external_match:
                return external_match
            return {
                "found": False,
                "barcode": barcode,
                "message": "No real barcode match was found in the current catalog or the barcode datasets.",
                "similar_products": [],
                "price_comparison": [],
            }

        candidates = _product_price_candidates(product)
        return {
            "found": True,
            "barcode": barcode,
            "match_type": "exact",
            "product": {
                "id": product.id,
                "name": product.name,
                "image_url": product.image_url,
                "category": product.category.name if product.category else None,
            },
            "confidence": 1.0,
            "similar_products": [],
            "price_comparison": candidates,
        }

    @staticmethod
    def get_amazon_reviews(product_id: int, limit: int = 5) -> Dict:
        _ensure_catalog_loaded()

        product = Product.objects.filter(id=product_id).first()
        if not product:
            return {
                "status": "product_not_found",
                "message": "Product not found.",
                "product_id": product_id,
                "reviews": [],
            }

        if not product.amazon_url:
            return {
                "status": "unavailable",
                "message": "No Amazon product URL is attached to this catalog row.",
                "product_id": product.id,
                "product_name": product.name,
                "reviews": [],
            }

        config = _amazon_review_api_config()
        if not config["enabled"]:
            return {
                "status": "not_configured",
                "message": "Amazon reviews are not configured yet. Set DEALSPHERE_AMAZON_REVIEWS_KEY in the backend environment.",
                "product_id": product.id,
                "product_name": product.name,
                "reviews": [],
            }

        asin = _extract_amazon_asin(product.amazon_url)
        if not asin:
            return {
                "status": "unavailable",
                "message": "Could not extract a valid ASIN from the stored Amazon product URL.",
                "product_id": product.id,
                "product_name": product.name,
                "reviews": [],
            }

        country = _amazon_country_from_url(product.amazon_url, default_country=str(config["default_country"]))
        request_url = f"{config['endpoint']}?{urlencode({'asin': asin, 'country': country})}"
        request = Request(
            request_url,
            headers={
                "Content-Type": "application/json",
                "x-rapidapi-host": str(config["host"]),
                "x-rapidapi-key": str(config["key"]),
            },
            method="GET",
        )

        try:
            with urlopen(request, timeout=int(config["timeout_seconds"])) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            error_body = ""
            try:
                error_body = exc.read().decode("utf-8", errors="ignore")
            except Exception:
                error_body = ""
            return {
                "status": "api_error",
                "message": "Amazon review provider returned an error response.",
                "product_id": product.id,
                "product_name": product.name,
                "asin": asin,
                "country": country,
                "reviews": [],
                "provider_status_code": exc.code,
                "provider_error": error_body[:500],
            }
        except URLError as exc:
            return {
                "status": "transport_error",
                "message": "Amazon review provider could not be reached from the backend.",
                "product_id": product.id,
                "product_name": product.name,
                "asin": asin,
                "country": country,
                "reviews": [],
                "provider_error": str(exc.reason or exc),
            }
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "status": "parse_error",
                "message": "Amazon review provider returned an unreadable response.",
                "product_id": product.id,
                "product_name": product.name,
                "asin": asin,
                "country": country,
                "reviews": [],
                "provider_error": str(exc),
            }

        data = payload.get("data") or {}
        reviews = _normalize_amazon_reviews(data.get("reviews"), max(1, min(int(limit or 5), 10)))

        return {
            "status": "ok" if str(payload.get("status", "")).upper() == "OK" else str(payload.get("status") or "ok").lower(),
            "message": "",
            "product_id": product.id,
            "product_name": product.name,
            "asin": str(data.get("asin") or asin),
            "country": str(data.get("country") or country),
            "domain": data.get("domain"),
            "request_id": payload.get("request_id"),
            "rating_distribution": _normalize_amazon_rating_distribution(data.get("rating_distribution")),
            "review_count": len(reviews),
            "reviews": reviews,
            "source": "rapidapi_openweb_ninja",
        }

    @staticmethod
    def get_amazon_product_snapshot(product_id: int) -> Dict:
        _ensure_catalog_loaded()

        product = Product.objects.filter(id=product_id).first()
        if not product:
            return {
                "status": "product_not_found",
                "message": "Product not found.",
                "product_id": product_id,
            }

        if not product.amazon_url:
            return {
                "status": "unavailable",
                "message": "No Amazon product URL is attached to this catalog row.",
                "product_id": product.id,
                "product_name": product.name,
            }

        config = _amazon_product_info_api_config()
        if not config["enabled"]:
            return {
                "status": "not_configured",
                "message": "Amazon product info is not configured yet. Set DEALSPHERE_AMAZON_PRODUCT_INFO_KEY in the backend environment.",
                "product_id": product.id,
                "product_name": product.name,
            }

        asin = _extract_amazon_asin(product.amazon_url)
        if not asin:
            return {
                "status": "unavailable",
                "message": "Could not extract a valid ASIN from the stored Amazon product URL.",
                "product_id": product.id,
                "product_name": product.name,
            }

        domain = _amazon_domain_from_url(product.amazon_url, default_domain=str(config["default_domain"]))
        request_url = f"{config['endpoint']}?{urlencode({'asin': asin, 'domain': domain})}"
        request = Request(
            request_url,
            headers={
                "Content-Type": "application/json",
                "x-rapidapi-host": str(config["host"]),
                "x-rapidapi-key": str(config["key"]),
            },
            method="GET",
        )

        try:
            with urlopen(request, timeout=int(config["timeout_seconds"])) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            error_body = ""
            try:
                error_body = exc.read().decode("utf-8", errors="ignore")
            except Exception:
                error_body = ""

            provider_message = ""
            if error_body:
                try:
                    provider_message = str((json.loads(error_body) or {}).get("message") or "")
                except json.JSONDecodeError:
                    provider_message = error_body

            return {
                "status": "provider_access_denied" if exc.code == 403 else "api_error",
                "message": provider_message or "Amazon product info provider returned an error response.",
                "product_id": product.id,
                "product_name": product.name,
                "asin": asin,
                "domain": domain,
                "provider_status_code": exc.code,
                "provider_error": error_body[:500],
            }
        except URLError as exc:
            return {
                "status": "transport_error",
                "message": "Amazon product info provider could not be reached from the backend.",
                "product_id": product.id,
                "product_name": product.name,
                "asin": asin,
                "domain": domain,
                "provider_error": str(exc.reason or exc),
            }
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "status": "parse_error",
                "message": "Amazon product info provider returned an unreadable response.",
                "product_id": product.id,
                "product_name": product.name,
                "asin": asin,
                "domain": domain,
                "provider_error": str(exc),
            }

        data = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
        if not isinstance(data, dict):
            data = {}

        current_price = _extract_numeric_price(
            _extract_first_non_empty(data, "exact_price", "price", "product_price", "current_price", "sale_price")
        )
        original_price = _extract_numeric_price(
            _extract_first_non_empty(data, "list_price", "product_original_price", "original_price", "was_price")
        )

        return {
            "status": str(payload.get("status") or "ok").lower() if isinstance(payload, dict) else "ok",
            "message": "",
            "product_id": product.id,
            "product_name": product.name,
            "asin": asin,
            "domain": domain,
            "provider_request_id": payload.get("request_id") if isinstance(payload, dict) else None,
            "live_title": _extract_first_non_empty(data, "title", "product_title", "name"),
            "live_brand": _extract_first_non_empty(data, "brand", "product_brand", "byline"),
            "current_price": current_price,
            "original_price": original_price,
            "currency_symbol": _extract_first_non_empty(data, "price_symbol", "currency_symbol"),
            "currency_code": _extract_first_non_empty(data, "currency", "currency_code"),
            "rating": _extract_numeric_price(_extract_first_non_empty(data, "rating", "product_star_rating", "stars")),
            "ratings_total": _extract_first_non_empty(data, "ratings_total", "product_num_ratings", "num_ratings"),
            "availability": _extract_first_non_empty(data, "availability", "product_availability", "stock", "delivery"),
            "location": _extract_first_non_empty(data, "location", "delivery_location"),
            "product_url": _extract_first_non_empty(data, "product_url", "url") or product.amazon_url,
            "image_url": _extract_first_non_empty(data, "product_photo", "image", "image_url", "photo") or product.image_url,
            "prime": bool(_extract_first_non_empty(data, "is_prime", "prime")),
            "amazon_choice": bool(_extract_first_non_empty(data, "is_amazon_choice")),
            "best_seller": bool(_extract_first_non_empty(data, "is_best_seller")),
            "sales_volume": _extract_first_non_empty(data, "number_of_people_bought", "sales_volume"),
            "description": _extract_first_non_empty(data, "description", "product_description"),
            "features": _normalize_feature_list(
                _extract_first_non_empty(data, "about_product", "features", "highlights", "bullet_points")
            ),
            "source": "rapidapi_amazon_pricing_and_product_info",
        }

    @staticmethod
    def market_insights(category: Optional[str] = None) -> Dict:
        _ensure_catalog_loaded()

        queryset = Product.objects.all()
        if category:
            queryset = queryset.filter(category__name__icontains=category)

        offers = Offer.objects.filter(is_active=True)
        if category:
            offers = offers.filter(product__category__name__icontains=category)

        return {
            "total_products": queryset.count(),
            "price_trends": {
                "min_price": float(offers.aggregate(min_price=Min("price"))["min_price"] or 0),
                "max_price": float(offers.aggregate(max_price=Max("price"))["max_price"] or 0),
                "avg_price": float(offers.aggregate(avg_price=Avg("price"))["avg_price"] or 0),
            },
            "best_deals": list(
                offers.select_related("product", "merchant").order_by("price").values(
                    "product__name", "merchant__shop_name", "price"
                )[:10]
            ),
            "price_drops_predicted": [],
        }

    @staticmethod
    def barcode_dataset_statistics() -> Dict:
        _ensure_catalog_loaded()
        stats = {
            "catalog_barcode_products": Product.objects.exclude(barcode__isnull=True).exclude(barcode="").count(),
            "catalog_price_history_rows": PriceHistory.objects.count(),
            "external_sources": [],
        }

        for source_name, candidate_paths in _external_barcode_sources():
            existing_path = next((path for path in candidate_paths if path.exists() and path.is_file()), None)
            stats["external_sources"].append(
                {
                    "source": source_name,
                    "available": bool(existing_path),
                    "path": str(existing_path) if existing_path else None,
                }
            )
        return stats

    @staticmethod
    def ai_engine_status() -> Dict:
        _ensure_catalog_loaded()
        visual_index = DatasetVisualSearchService.dataset_index()
        return {
            "catalog_loaded": True,
            "ml_weights": get_ml_weights(),
            "visual_search": {
                "dataset_available": visual_index.get("reference_images", 0) > 0,
                "reference_images": visual_index.get("reference_images", 0),
                "category_count": visual_index.get("category_count", 0),
            },
            "price_history_records": PriceHistory.objects.count(),
            "market_sources": {
                "amazon_products": Product.objects.filter(amazon_price__isnull=False).count(),
                "flipkart_products": Product.objects.filter(flipkart_price__isnull=False).count(),
                "myntra_products": Product.objects.filter(myntra_price__isnull=False).count(),
                "local_offers": Offer.objects.filter(is_active=True).count(),
            },
        }
