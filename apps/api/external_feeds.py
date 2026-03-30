"""External retail feed adapters."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from django.conf import settings


def _external_fashion_feed_config() -> Dict[str, object]:
    config = getattr(settings, "EXTERNAL_FASHION_FEED_SETTINGS", {}) or {}
    timeout = int(config.get("timeout_seconds", 12) or 12)
    return {
        "female_footwear_endpoint": str(config.get("female_footwear_endpoint", "")).strip(),
        "timeout_seconds": max(timeout, 1),
    }


def _product_price_history_api_config() -> Dict[str, object]:
    config = getattr(settings, "PRODUCT_PRICE_HISTORY_API_SETTINGS", {}) or {}
    timeout = int(config.get("timeout_seconds", 12) or 12)
    return {
        "endpoint": str(config.get("endpoint", "")).strip(),
        "host": str(config.get("host", "")).strip(),
        "key": str(config.get("key", "")).strip(),
        "default_country": str(config.get("default_country", "us")).strip().lower() or "us",
        "default_language": str(config.get("default_language", "en")).strip().lower() or "en",
        "timeout_seconds": max(timeout, 1),
        "enabled": bool(config.get("enabled", False)),
    }


def _extract_price_value(value) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    cleaned = re.sub(r"[^0-9.,-]", "", str(value))
    if not cleaned:
        return None
    if cleaned.count(",") and not cleaned.count("."):
        cleaned = cleaned.replace(",", "")
    elif cleaned.count(",") and cleaned.count("."):
        cleaned = cleaned.replace(",", "")
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return None


def _first_non_empty(mapping: Dict | None, *keys):
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _normalize_history_points(raw_points, default_currency: str | None = None) -> List[Dict]:
    points: List[Dict] = []
    for item in list(raw_points or []):
        if isinstance(item, dict):
            price = _extract_price_value(
                _first_non_empty(
                    item,
                    "price",
                    "value",
                    "amount",
                    "current_price",
                    "product_price",
                    "sale_price",
                    "selling_price",
                )
            )
            if price is None:
                continue
            points.append(
                {
                    "date": str(
                        _first_non_empty(
                            item,
                            "date",
                            "datetime",
                            "timestamp",
                            "time",
                            "recorded_at",
                            "day",
                        )
                        or ""
                    ).strip()
                    or None,
                    "price": price,
                    "currency": str(
                        _first_non_empty(
                            item,
                            "currency",
                            "currency_symbol",
                            "currency_code",
                            "symbol",
                        )
                        or default_currency
                        or ""
                    ).strip()
                    or None,
                    "label": str(
                        _first_non_empty(item, "label", "title", "note", "event") or ""
                    ).strip()
                    or None,
                }
            )
            continue

        if isinstance(item, (list, tuple)) and len(item) >= 2:
            price = _extract_price_value(item[1])
            if price is None:
                continue
            points.append(
                {
                    "date": str(item[0]).strip() or None,
                    "price": price,
                    "currency": default_currency,
                    "label": None,
                }
            )
    return points


class ExternalFashionFeedService:
    @staticmethod
    def get_female_footwear(limit: int = 48) -> Dict:
        config = _external_fashion_feed_config()
        endpoint = str(config["female_footwear_endpoint"])
        if not endpoint:
            return {
                "status": "not_configured",
                "message": "Female footwear feed endpoint is not configured.",
                "items": [],
                "count": 0,
            }

        request = Request(endpoint, headers={"Content-Type": "application/json"}, method="GET")
        try:
            with urlopen(request, timeout=int(config["timeout_seconds"])) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            return {
                "status": "api_error",
                "message": "Female footwear provider returned an error response.",
                "provider_status_code": exc.code,
                "items": [],
                "count": 0,
            }
        except URLError as exc:
            return {
                "status": "transport_error",
                "message": "Female footwear provider could not be reached from the backend.",
                "provider_error": str(exc.reason or exc),
                "items": [],
                "count": 0,
            }
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "status": "parse_error",
                "message": "Female footwear provider returned an unreadable response.",
                "provider_error": str(exc),
                "items": [],
                "count": 0,
            }

        raw_items = list((payload or {}).get("value") or [])
        normalized_items: List[Dict] = []
        for index, item in enumerate(raw_items[: max(1, min(int(limit or 48), 100))], start=1):
            normalized_items.append(
                {
                    "id": item.get("Unnamed: 0", index),
                    "brand": str(item.get("Brand") or "").strip(),
                    "description": str(item.get("Description") or "").strip(),
                    "image_url": item.get("Image"),
                    "price_text": str(item.get("Price") or "").strip(),
                    "price_value": _extract_price_value(item.get("Price")),
                    "tag": str(item.get("Tag") or "").strip(),
                }
            )

        return {
            "status": "ok",
            "message": "",
            "items": normalized_items,
            "count": int((payload or {}).get("Count") or len(normalized_items)),
            "source": "ecommerceflaskapi_femalefootwear",
        }


class RealTimeProductSearchService:
    """Adapter for the RapidAPI real-time product search price-history endpoint."""

    @classmethod
    def get_product_price_history(
        cls,
        provider_product_id: str,
        country: str | None = None,
        language: str | None = None,
    ) -> Dict:
        config = _product_price_history_api_config()
        if not config["enabled"]:
            return {
                "status": "not_configured",
                "message": "Product price history API is not configured yet. Set DEALSPHERE_PRODUCT_PRICE_HISTORY_KEY in the backend environment.",
                "product_id": provider_product_id,
                "history": [],
                "point_count": 0,
            }

        normalized_country = str(country or config["default_country"]).strip().lower() or str(config["default_country"])
        normalized_language = str(language or config["default_language"]).strip().lower() or str(config["default_language"])
        request_url = f"{config['endpoint']}?{urlencode({'product_id': provider_product_id, 'country': normalized_country, 'language': normalized_language})}"
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
                "message": "Product price history provider returned an error response.",
                "product_id": provider_product_id,
                "country": normalized_country,
                "language": normalized_language,
                "history": [],
                "point_count": 0,
                "provider_status_code": exc.code,
                "provider_error": error_body[:500],
            }
        except URLError as exc:
            return {
                "status": "transport_error",
                "message": "Product price history provider could not be reached from the backend.",
                "product_id": provider_product_id,
                "country": normalized_country,
                "language": normalized_language,
                "history": [],
                "point_count": 0,
                "provider_error": str(exc.reason or exc),
            }
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "status": "parse_error",
                "message": "Product price history provider returned an unreadable response.",
                "product_id": provider_product_id,
                "country": normalized_country,
                "language": normalized_language,
                "history": [],
                "point_count": 0,
                "provider_error": str(exc),
            }

        return cls._normalize_price_history_payload(
            payload=payload,
            provider_product_id=provider_product_id,
            country=normalized_country,
            language=normalized_language,
        )

    @staticmethod
    def _normalize_price_history_payload(
        payload: Dict,
        provider_product_id: str,
        country: str,
        language: str,
    ) -> Dict:
        data = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
        raw_history = []
        title = None
        brand = None
        currency = None
        latest_price = None

        if isinstance(data, dict):
            raw_history = (
                _first_non_empty(
                    data,
                    "price_history",
                    "prices_history",
                    "history",
                    "product_price_history",
                    "priceHistory",
                    "prices",
                )
                or []
            )
            title = _first_non_empty(data, "product_title", "title", "name", "product_name")
            brand = _first_non_empty(data, "brand", "product_brand")
            currency = _first_non_empty(data, "currency", "currency_code", "currency_symbol")
            latest_price = _extract_price_value(
                _first_non_empty(
                    data,
                    "current_price",
                    "price",
                    "product_price",
                    "latest_price",
                    "sale_price",
                )
            )
        elif isinstance(data, list):
            raw_history = data

        history = _normalize_history_points(raw_history, default_currency=str(currency or "").strip() or None)
        if latest_price is None and history:
            latest_price = history[-1]["price"]

        prices = [point["price"] for point in history if point.get("price") is not None]
        lowest_price = min(prices) if prices else latest_price
        highest_price = max(prices) if prices else latest_price

        return {
            "status": str(payload.get("status") or "ok").lower() if isinstance(payload, dict) else "ok",
            "message": "",
            "product_id": provider_product_id,
            "country": country,
            "language": language,
            "provider_request_id": payload.get("request_id") if isinstance(payload, dict) else None,
            "title": str(title or "").strip() or None,
            "brand": str(brand or "").strip() or None,
            "latest_price": latest_price,
            "lowest_price": lowest_price,
            "highest_price": highest_price,
            "currency": str(currency or "").strip() or (history[0]["currency"] if history and history[0].get("currency") else None),
            "point_count": len(history),
            "history": history,
            "source": "rapidapi_real_time_product_search",
        }


def _realtime_product_api_config() -> Dict:
    cfg = getattr(settings, "REALTIME_PRODUCT_API_SETTINGS", {}) or {}
    timeout = int(cfg.get("timeout_seconds", 12) or 12)
    return {
        "endpoint": str(cfg.get("endpoint", "")).strip(),
        "host": str(cfg.get("host", "")).strip(),
        "key": str(cfg.get("key", "")).strip(),
        "timeout_seconds": max(timeout, 1),
        "enabled": bool(cfg.get("enabled", False)),
    }


class RealTimePriceService:
    """
    Fetches live product details from Amazon / Flipkart / Myntra / AJIO / Croma
    via the RapidAPI realtime product-details endpoint.

    Usage:
        results = RealTimePriceService.fetch_live_prices(product)
        # returns a list of dicts, one per URL that was resolved
    """

    @classmethod
    def fetch_product(cls, url: str) -> Dict:
        """Call the API for a single retailer URL and return a normalised dict."""
        config = _realtime_product_api_config()
        if not config["enabled"]:
            return {"status": "not_configured", "url": url, "message": "RealTime product API key not set."}

        request_url = f"{config['endpoint']}?url={quote(url, safe='')}"
        req = Request(
            request_url,
            headers={
                "Content-Type": "application/json",
                "x-rapidapi-host": config["host"],
                "x-rapidapi-key": config["key"],
            },
            method="GET",
        )
        try:
            with urlopen(req, timeout=config["timeout_seconds"]) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return cls._normalize(payload, url)
        except HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="ignore")[:300]
            except Exception:
                pass
            return {
                "status": "api_error",
                "url": url,
                "message": "Provider returned an error response.",
                "provider_status_code": exc.code,
                "provider_error": body,
            }
        except URLError as exc:
            return {
                "status": "transport_error",
                "url": url,
                "message": "Could not reach the product details provider.",
                "provider_error": str(exc.reason or exc),
            }
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "status": "parse_error",
                "url": url,
                "message": "Provider returned an unreadable response.",
                "provider_error": str(exc),
            }

    @classmethod
    def fetch_live_prices(cls, product) -> List[Dict]:
        """
        Fetch live prices for all retailer URLs attached to a product, in parallel.
        Falls back to search URLs built from the product name when direct URLs are absent.
        Returns a list sorted by price (cheapest first), unavailable sources appended last.
        """
        product_name = str(getattr(product, "name", "") or "").strip()
        encoded_name = quote(product_name, safe="") if product_name else ""

        url_map = []
        if getattr(product, "amazon_url", None):
            url_map.append(("amazon", "Amazon", product.amazon_url))
        elif encoded_name:
            url_map.append(("amazon", "Amazon", f"https://www.amazon.in/s?k={encoded_name}"))

        if getattr(product, "flipkart_url", None):
            url_map.append(("flipkart", "Flipkart", product.flipkart_url))
        elif encoded_name:
            url_map.append(("flipkart", "Flipkart", f"https://www.flipkart.com/search?q={encoded_name}"))

        if getattr(product, "myntra_url", None):
            url_map.append(("myntra", "Myntra", product.myntra_url))
        elif encoded_name:
            url_map.append(("myntra", "Myntra", f"https://www.myntra.com/{encoded_name.replace('%20', '-')}"))

        if not url_map:
            return []

        results: List[Dict] = []

        def _fetch_one(source: str, source_name: str, url: str) -> Dict:
            data = cls.fetch_product(url)
            data.setdefault("source", source)
            data.setdefault("source_name", source_name)
            data["source"] = source
            data["source_name"] = source_name
            return data

        with ThreadPoolExecutor(max_workers=len(url_map)) as pool:
            futures = {
                pool.submit(_fetch_one, src, name, url): src
                for src, name, url in url_map
            }
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception:
                    pass

        # Sort: ok results by price first, then anything else
        ok = sorted(
            [r for r in results if r.get("status") == "ok" and r.get("price") is not None],
            key=lambda r: r["price"],
        )
        rest = [r for r in results if r not in ok]
        return ok + rest

    @staticmethod
    def _normalize(data: Dict, url: str) -> Dict:
        """Map the raw API payload to a consistent structure."""
        # Price — try several common field names
        price = None
        for key in ("product_price", "price", "selling_price", "discounted_price", "sale_price"):
            raw = data.get(key)
            if raw is not None:
                price = _extract_price_value(raw)
                if price:
                    break

        original_price = None
        for key in ("product_original_price", "original_price", "mrp", "marked_price", "market_price"):
            raw = data.get(key)
            if raw is not None:
                original_price = _extract_price_value(raw)
                if original_price:
                    break

        discount_percent = None
        if price and original_price and original_price > price:
            discount_percent = round(((original_price - price) / original_price) * 100, 1)

        # Rating
        rating = None
        for key in ("product_rating", "rating", "average_rating", "stars"):
            raw = data.get(key)
            if raw is not None:
                try:
                    rating = round(float(str(raw).split("/")[0].strip()), 1)
                    break
                except (ValueError, AttributeError):
                    pass

        # Images
        images = data.get("product_images") or data.get("images") or data.get("image") or []
        if isinstance(images, str):
            images = [images]

        # Title
        title = (
            data.get("product_title")
            or data.get("title")
            or data.get("name")
            or data.get("product_name")
            or ""
        ).strip()

        return {
            "status": "ok",
            "url": url,
            "title": title,
            "price": price,
            "original_price": original_price,
            "discount_percent": discount_percent,
            "rating": rating,
            "review_count": (
                data.get("product_review_count")
                or data.get("review_count")
                or data.get("ratings_total")
                or data.get("num_reviews")
            ),
            "availability": (
                data.get("product_availability")
                or data.get("availability")
                or data.get("in_stock")
            ),
            "image_url": images[0] if images else None,
            "brand": (data.get("brand") or data.get("product_brand") or "").strip() or None,
            "specs": data.get("product_specifications") or data.get("specifications") or [],
        }
