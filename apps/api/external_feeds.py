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


def _real_time_product_search_api_config() -> Dict[str, object]:
    config = getattr(settings, "REALTIME_PRODUCT_SEARCH_API_SETTINGS", {}) or {}
    fallback = _product_price_history_api_config()
    timeout = int(config.get("timeout_seconds", fallback["timeout_seconds"]) or fallback["timeout_seconds"])
    return {
        "host": str(config.get("host", fallback["host"])).strip(),
        "key": str(config.get("key", fallback["key"])).strip(),
        "search_endpoint": str(config.get("search_endpoint", "")).strip(),
        "product_details_endpoint": str(config.get("product_details_endpoint", "")).strip(),
        "product_offers_endpoint": str(config.get("product_offers_endpoint", "")).strip(),
        "product_price_history_endpoint": str(
            config.get("product_price_history_endpoint", fallback["endpoint"])
        ).strip(),
        "deals_endpoint": str(config.get("deals_endpoint", "")).strip(),
        "default_country": str(
            config.get("default_country", fallback["default_country"])
        ).strip().lower()
        or str(fallback["default_country"]),
        "default_language": str(
            config.get("default_language", fallback["default_language"])
        ).strip().lower()
        or str(fallback["default_language"]),
        "timeout_seconds": max(timeout, 1),
        "enabled": bool(config.get("enabled", False)) or bool(
            str(config.get("host", fallback["host"])).strip()
            and str(config.get("key", fallback["key"])).strip()
        ),
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
                    "store": None,
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
                    "store": None,
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
    """Adapter for the RapidAPI real-time product search endpoints."""

    SOURCE_NAME = "rapidapi_real_time_product_search"
    NOT_CONFIGURED_MESSAGE = (
        "Real-time product search API is not configured yet. "
        "Set DEALSPHERE_REALTIME_PRODUCT_SEARCH_KEY or DEALSPHERE_PRODUCT_PRICE_HISTORY_KEY "
        "in the backend environment."
    )

    @classmethod
    def _config(cls) -> Dict[str, object]:
        return _real_time_product_search_api_config()

    @staticmethod
    def _clean_text(value) -> str | None:
        text = str(value or "").strip()
        return text or None

    @classmethod
    def _normalize_status(cls, payload: Dict | None, default: str = "ok") -> str:
        if not isinstance(payload, dict):
            return default
        status_value = cls._clean_text(payload.get("status"))
        return status_value.lower() if status_value else default

    @staticmethod
    def _extract_int(value) -> int | None:
        if value in (None, "", [], {}):
            return None
        try:
            return int(float(str(value).replace(",", "").strip()))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_rating(value) -> float | None:
        if value in (None, "", [], {}):
            return None
        try:
            return round(float(str(value).split("/")[0].replace(",", "").strip()), 2)
        except (TypeError, ValueError, AttributeError):
            return None

    @classmethod
    def _extract_string_list(cls, value) -> List[str]:
        if value in (None, "", [], {}):
            return []
        if isinstance(value, str):
            text = cls._clean_text(value)
            return [text] if text else []

        values: List[str] = []
        for item in list(value):
            if isinstance(item, dict):
                text = cls._clean_text(
                    _first_non_empty(item, "label", "title", "name", "value", "text")
                )
            else:
                text = cls._clean_text(item)
            if text:
                values.append(text)
        return values

    @classmethod
    def _extract_image_urls(cls, mapping: Dict | None) -> List[str]:
        if not isinstance(mapping, dict):
            return []

        images: List[str] = []

        def _append(value):
            if isinstance(value, dict):
                value = _first_non_empty(value, "url", "link", "src", "image", "photo")
            text = cls._clean_text(value)
            if text and text not in images:
                images.append(text)

        _append(
            _first_non_empty(
                mapping,
                "product_photo",
                "image_url",
                "image",
                "thumbnail",
                "thumbnail_url",
            )
        )

        gallery = _first_non_empty(
            mapping,
            "product_photos",
            "photos",
            "images",
            "product_images",
            "gallery",
        )
        if isinstance(gallery, (list, tuple)):
            for item in gallery:
                _append(item)
        elif gallery not in (None, "", [], {}):
            _append(gallery)

        return images

    @classmethod
    def _extract_pricing(cls, *mappings: Dict | None) -> tuple[float | None, float | None, str | None]:
        current_price = None
        original_price = None
        currency = None

        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
            if current_price is None:
                current_price = _extract_price_value(
                    _first_non_empty(
                        mapping,
                        "price",
                        "current_price",
                        "offer_price",
                        "product_price",
                        "sale_price",
                        "selling_price",
                        "extracted_price",
                    )
                )
            if original_price is None:
                original_price = _extract_price_value(
                    _first_non_empty(
                        mapping,
                        "original_price",
                        "list_price",
                        "compare_at_price",
                        "old_price",
                        "market_price",
                        "mrp",
                        "typical_price",
                    )
                )
            if not currency:
                currency = cls._clean_text(
                    _first_non_empty(
                        mapping,
                        "currency",
                        "currency_code",
                        "currency_symbol",
                        "price_symbol",
                    )
                )

        return current_price, original_price, currency

    @classmethod
    def _normalize_filters(cls, raw_filters) -> List[Dict]:
        groups: List[Dict] = []
        if isinstance(raw_filters, dict):
            iterable = [
                {"key": key, "label": str(key).replace("_", " ").title(), "options": value}
                for key, value in raw_filters.items()
            ]
        else:
            iterable = list(raw_filters or [])

        for raw_group in iterable:
            if not isinstance(raw_group, dict):
                continue
            group_key = cls._clean_text(
                _first_non_empty(raw_group, "key", "id", "filter_name", "name", "label", "title")
            )
            group_label = cls._clean_text(
                _first_non_empty(raw_group, "label", "name", "title", "filter_name")
            ) or group_key
            raw_options = _first_non_empty(raw_group, "options", "values", "items", "filter_values") or []
            if isinstance(raw_options, dict):
                raw_options = [
                    {"value": key, "label": str(key), "count": value}
                    for key, value in raw_options.items()
                ]

            options = []
            for option in list(raw_options):
                if isinstance(option, dict):
                    value = cls._clean_text(
                        _first_non_empty(option, "value", "id", "key", "name", "label", "text")
                    )
                    label = cls._clean_text(
                        _first_non_empty(option, "label", "name", "text", "value")
                    ) or value
                    count = cls._extract_int(
                        _first_non_empty(option, "count", "product_count", "results", "total")
                    )
                else:
                    value = cls._clean_text(option)
                    label = value
                    count = None
                if value or label:
                    options.append({"value": value, "label": label, "count": count})

            groups.append({"key": group_key, "label": group_label, "options": options})

        return groups

    @classmethod
    def _normalize_product_item(cls, item: Dict | None) -> Dict | None:
        if not isinstance(item, dict):
            return None

        offer = item.get("offer") if isinstance(item.get("offer"), dict) else {}
        merchant = item.get("merchant") if isinstance(item.get("merchant"), dict) else {}
        seller = item.get("seller") if isinstance(item.get("seller"), dict) else {}
        current_price, original_price, currency = cls._extract_pricing(offer, merchant, seller, item)
        images = cls._extract_image_urls(item)

        return {
            "product_id": cls._clean_text(
                _first_non_empty(item, "product_id", "id", "offer_id", "docid", "item_id")
            ),
            "title": cls._clean_text(
                _first_non_empty(item, "product_title", "title", "name", "product_name")
            ),
            "brand": cls._clean_text(_first_non_empty(item, "brand", "product_brand")),
            "store": cls._clean_text(
                _first_non_empty(offer, "store_name", "store", "merchant", "source", "seller_name")
                or _first_non_empty(item, "store_name", "store", "merchant", "source")
            ),
            "seller": cls._clean_text(
                _first_non_empty(seller, "name", "seller_name", "title")
                or _first_non_empty(item, "seller_name", "seller")
            ),
            "current_price": current_price,
            "original_price": original_price,
            "currency": currency,
            "rating": cls._extract_rating(
                _first_non_empty(item, "rating", "product_rating", "average_rating", "stars")
            ),
            "reviews_count": cls._extract_int(
                _first_non_empty(
                    item,
                    "reviews_count",
                    "review_count",
                    "ratings_total",
                    "rating_count",
                    "num_reviews",
                    "reviews",
                )
            ),
            "availability": cls._clean_text(
                _first_non_empty(offer, "availability", "stock_status", "in_stock")
                or _first_non_empty(item, "availability", "stock_status", "in_stock")
            ),
            "product_condition": cls._clean_text(
                _first_non_empty(offer, "product_condition", "condition")
                or _first_non_empty(item, "product_condition", "condition")
            ),
            "product_url": cls._clean_text(
                _first_non_empty(offer, "offer_page_url", "url", "product_url", "page_url")
                or _first_non_empty(
                    item,
                    "product_page_url",
                    "product_url",
                    "url",
                    "offer_page_url",
                    "page_url",
                )
            ),
            "image_url": images[0] if images else None,
            "badges": cls._extract_string_list(_first_non_empty(item, "badges", "labels", "tags")),
            "raw_offer_count": cls._extract_int(
                _first_non_empty(item, "offers_count", "offer_count", "total_offers")
            ),
        }

    @classmethod
    def _perform_request(
        cls,
        endpoint: str,
        params: Dict[str, object],
        *,
        context: Dict | None = None,
        message: str | None = None,
    ) -> Dict:
        config = cls._config()
        response_base = dict(context or {})

        if not config["enabled"]:
            return {
                "status": "not_configured",
                "message": cls.NOT_CONFIGURED_MESSAGE,
                **response_base,
            }

        if not endpoint:
            return {
                "status": "not_configured",
                "message": message or "Real-time product search endpoint is not configured.",
                **response_base,
            }

        query_string = urlencode(
            {key: value for key, value in params.items() if value not in (None, "")},
            doseq=True,
        )
        request_url = f"{endpoint}?{query_string}" if query_string else endpoint
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
                "message": "Real-time product search provider returned an error response.",
                **response_base,
                "provider_status_code": exc.code,
                "provider_error": error_body[:500],
            }
        except URLError as exc:
            return {
                "status": "transport_error",
                "message": "Real-time product search provider could not be reached from the backend.",
                **response_base,
                "provider_error": str(exc.reason or exc),
            }
        except (OSError, json.JSONDecodeError) as exc:
            return {
                "status": "parse_error",
                "message": "Real-time product search provider returned an unreadable response.",
                **response_base,
                "provider_error": str(exc),
            }

        return {
            "status": "ok",
            "payload": payload,
            "config": config,
            **response_base,
        }

    @classmethod
    def search_products_v2(
        cls,
        query: str,
        country: str | None = None,
        language: str | None = None,
        page: int = 1,
        limit: int = 10,
        sort_by: str = "BEST_MATCH",
        product_condition: str = "ANY",
        return_filters: bool = True,
    ) -> Dict:
        config = cls._config()
        normalized_country = cls._clean_text(country) or str(config["default_country"])
        normalized_language = cls._clean_text(language) or str(config["default_language"])
        normalized_page = max(int(page or 1), 1)
        normalized_limit = max(int(limit or 10), 1)
        request_result = cls._perform_request(
            str(config["search_endpoint"]),
            {
                "q": query,
                "country": normalized_country,
                "language": normalized_language,
                "page": normalized_page,
                "limit": normalized_limit,
                "sort_by": sort_by,
                "product_condition": product_condition,
                "return_filters": str(bool(return_filters)).lower(),
            },
            context={
                "query": query,
                "country": normalized_country,
                "language": normalized_language,
                "page": normalized_page,
                "limit": normalized_limit,
                "sort_by": sort_by,
                "product_condition": product_condition,
                "products": [],
                "filters": [],
                "count": 0,
            },
        )
        if request_result.get("status") != "ok":
            return request_result
        return cls._normalize_search_payload(
            payload=request_result["payload"],
            query=query,
            country=normalized_country,
            language=normalized_language,
            page=normalized_page,
            limit=normalized_limit,
            sort_by=sort_by,
            product_condition=product_condition,
        )

    @classmethod
    def get_product_details_v2(
        cls,
        provider_product_id: str,
        country: str | None = None,
        language: str | None = None,
    ) -> Dict:
        config = cls._config()
        normalized_country = cls._clean_text(country) or str(config["default_country"])
        normalized_language = cls._clean_text(language) or str(config["default_language"])
        request_result = cls._perform_request(
            str(config["product_details_endpoint"]),
            {
                "product_id": provider_product_id,
                "country": normalized_country,
                "language": normalized_language,
            },
            context={
                "product_id": provider_product_id,
                "country": normalized_country,
                "language": normalized_language,
                "images": [],
                "features": [],
                "specifications": None,
            },
        )
        if request_result.get("status") != "ok":
            return request_result
        return cls._normalize_product_details_payload(
            payload=request_result["payload"],
            provider_product_id=provider_product_id,
            country=normalized_country,
            language=normalized_language,
        )

    @classmethod
    def get_product_offers_v2(
        cls,
        provider_product_id: str,
        page: int = 1,
        country: str | None = None,
        language: str | None = None,
    ) -> Dict:
        config = cls._config()
        normalized_country = cls._clean_text(country) or str(config["default_country"])
        normalized_language = cls._clean_text(language) or str(config["default_language"])
        normalized_page = max(int(page or 1), 1)
        request_result = cls._perform_request(
            str(config["product_offers_endpoint"]),
            {
                "product_id": provider_product_id,
                "page": normalized_page,
                "country": normalized_country,
                "language": normalized_language,
            },
            context={
                "product_id": provider_product_id,
                "country": normalized_country,
                "language": normalized_language,
                "page": normalized_page,
                "offers": [],
                "offers_count": 0,
            },
        )
        if request_result.get("status") != "ok":
            return request_result
        return cls._normalize_product_offers_payload(
            payload=request_result["payload"],
            provider_product_id=provider_product_id,
            country=normalized_country,
            language=normalized_language,
            page=normalized_page,
        )

    @classmethod
    def get_product_price_history(
        cls,
        provider_product_id: str,
        country: str | None = None,
        language: str | None = None,
    ) -> Dict:
        config = cls._config()
        normalized_country = cls._clean_text(country) or str(config["default_country"])
        normalized_language = cls._clean_text(language) or str(config["default_language"])
        request_result = cls._perform_request(
            str(config["product_price_history_endpoint"]),
            {
                "product_id": provider_product_id,
                "country": normalized_country,
                "language": normalized_language,
            },
            context={
                "product_id": provider_product_id,
                "country": normalized_country,
                "language": normalized_language,
                "history": [],
                "series": [],
                "point_count": 0,
            },
        )
        if request_result.get("status") != "ok":
            return request_result
        return cls._normalize_price_history_payload(
            payload=request_result["payload"],
            provider_product_id=provider_product_id,
            country=normalized_country,
            language=normalized_language,
        )

    @classmethod
    def get_deals_v2(
        cls,
        query: str,
        country: str | None = None,
        language: str | None = None,
        page: int = 1,
        limit: int = 10,
        sort_by: str = "BEST_MATCH",
        product_condition: str = "ANY",
    ) -> Dict:
        config = cls._config()
        normalized_country = cls._clean_text(country) or str(config["default_country"])
        normalized_language = cls._clean_text(language) or str(config["default_language"])
        normalized_page = max(int(page or 1), 1)
        normalized_limit = max(int(limit or 10), 1)
        request_result = cls._perform_request(
            str(config["deals_endpoint"]),
            {
                "q": query,
                "country": normalized_country,
                "language": normalized_language,
                "page": normalized_page,
                "limit": normalized_limit,
                "sort_by": sort_by,
                "product_condition": product_condition,
            },
            context={
                "query": query,
                "country": normalized_country,
                "language": normalized_language,
                "page": normalized_page,
                "limit": normalized_limit,
                "sort_by": sort_by,
                "product_condition": product_condition,
                "deals": [],
                "count": 0,
            },
        )
        if request_result.get("status") != "ok":
            return request_result
        return cls._normalize_deals_payload(
            payload=request_result["payload"],
            query=query,
            country=normalized_country,
            language=normalized_language,
            page=normalized_page,
            limit=normalized_limit,
            sort_by=sort_by,
            product_condition=product_condition,
        )

    @classmethod
    def _normalize_search_payload(
        cls,
        payload: Dict,
        query: str,
        country: str,
        language: str,
        page: int,
        limit: int,
        sort_by: str,
        product_condition: str,
    ) -> Dict:
        data = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
        raw_items = []
        raw_filters = []
        count = 0
        if isinstance(data, dict):
            raw_items = (
                _first_non_empty(
                    data,
                    "products",
                    "results",
                    "items",
                    "shopping_results",
                    "search_results",
                )
                or []
            )
            raw_filters = _first_non_empty(data, "filters", "available_filters") or []
            count = cls._extract_int(
                _first_non_empty(
                    data,
                    "total_products",
                    "total_results",
                    "count",
                    "total_count",
                    "result_count",
                )
            ) or 0
        elif isinstance(data, list):
            raw_items = data

        products = [item for item in (cls._normalize_product_item(entry) for entry in list(raw_items or [])) if item]
        return {
            "status": cls._normalize_status(payload),
            "message": cls._clean_text(payload.get("message") if isinstance(payload, dict) else None) or "",
            "query": query,
            "country": country,
            "language": language,
            "page": page,
            "limit": limit,
            "sort_by": sort_by,
            "product_condition": product_condition,
            "provider_request_id": payload.get("request_id") if isinstance(payload, dict) else None,
            "count": count or len(products),
            "products": products,
            "filters": cls._normalize_filters(raw_filters),
            "source": cls.SOURCE_NAME,
        }

    @classmethod
    def _normalize_product_details_payload(
        cls,
        payload: Dict,
        provider_product_id: str,
        country: str,
        language: str,
    ) -> Dict:
        data = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            data = {}

        offer = data.get("offer") if isinstance(data.get("offer"), dict) else {}
        current_price, original_price, currency = cls._extract_pricing(offer, data)
        images = cls._extract_image_urls(data)

        return {
            "status": cls._normalize_status(payload),
            "message": cls._clean_text(payload.get("message") if isinstance(payload, dict) else None) or "",
            "product_id": provider_product_id,
            "country": country,
            "language": language,
            "provider_request_id": payload.get("request_id") if isinstance(payload, dict) else None,
            "title": cls._clean_text(
                _first_non_empty(data, "product_title", "title", "name", "product_name")
            ),
            "brand": cls._clean_text(_first_non_empty(data, "brand", "product_brand")),
            "description": cls._clean_text(
                _first_non_empty(data, "description", "product_description", "about_this_item")
            ),
            "current_price": current_price,
            "original_price": original_price,
            "currency": currency,
            "rating": cls._extract_rating(
                _first_non_empty(data, "rating", "product_rating", "average_rating", "stars")
            ),
            "reviews_count": cls._extract_int(
                _first_non_empty(
                    data,
                    "reviews_count",
                    "review_count",
                    "ratings_total",
                    "rating_count",
                    "num_reviews",
                )
            ),
            "availability": cls._clean_text(
                _first_non_empty(offer, "availability", "stock_status", "in_stock")
                or _first_non_empty(data, "availability", "stock_status", "in_stock")
            ),
            "store": cls._clean_text(
                _first_non_empty(offer, "store_name", "store", "merchant")
                or _first_non_empty(data, "store_name", "store", "merchant")
            ),
            "product_condition": cls._clean_text(
                _first_non_empty(offer, "product_condition", "condition")
                or _first_non_empty(data, "product_condition", "condition")
            ),
            "product_url": cls._clean_text(
                _first_non_empty(
                    data,
                    "product_page_url",
                    "product_url",
                    "url",
                    "offer_page_url",
                    "page_url",
                )
            ),
            "image_url": images[0] if images else None,
            "images": images,
            "features": cls._extract_string_list(
                _first_non_empty(data, "features", "feature_bullets", "highlights")
            ),
            "specifications": _first_non_empty(
                data,
                "specifications",
                "product_specifications",
                "attributes",
                "specs",
            ),
            "source": cls.SOURCE_NAME,
        }

    @classmethod
    def _normalize_product_offers_payload(
        cls,
        payload: Dict,
        provider_product_id: str,
        country: str,
        language: str,
        page: int,
    ) -> Dict:
        data = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
        if not isinstance(data, dict):
            data = {}

        raw_offers = (
            _first_non_empty(data, "offers", "product_offers", "buying_options", "results")
            or []
        )
        if isinstance(raw_offers, dict):
            raw_offers = list(raw_offers.values())

        offers = []
        for item in list(raw_offers or []):
            if not isinstance(item, dict):
                continue
            current_price, original_price, currency = cls._extract_pricing(item)
            offers.append(
                {
                    "store": cls._clean_text(
                        _first_non_empty(item, "store_name", "store", "merchant", "seller_name")
                    ),
                    "seller": cls._clean_text(_first_non_empty(item, "seller_name", "seller", "merchant")),
                    "current_price": current_price,
                    "original_price": original_price,
                    "currency": currency,
                    "availability": cls._clean_text(
                        _first_non_empty(item, "availability", "stock_status", "in_stock")
                    ),
                    "shipping": cls._clean_text(
                        _first_non_empty(item, "shipping", "shipping_text", "delivery", "shipping_cost")
                    ),
                    "offer_url": cls._clean_text(
                        _first_non_empty(item, "offer_page_url", "product_url", "url", "page_url")
                    ),
                    "product_condition": cls._clean_text(
                        _first_non_empty(item, "product_condition", "condition")
                    ),
                }
            )

        return {
            "status": cls._normalize_status(payload),
            "message": cls._clean_text(payload.get("message") if isinstance(payload, dict) else None) or "",
            "product_id": provider_product_id,
            "country": country,
            "language": language,
            "page": page,
            "provider_request_id": payload.get("request_id") if isinstance(payload, dict) else None,
            "title": cls._clean_text(
                _first_non_empty(data, "product_title", "title", "name", "product_name")
            ),
            "offers_count": cls._extract_int(
                _first_non_empty(data, "offers_count", "offer_count", "total_offers")
            )
            or len(offers),
            "offers": offers,
            "source": cls.SOURCE_NAME,
        }

    @classmethod
    def _normalize_price_history_payload(
        cls,
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

        history = []
        series = []
        if raw_history and all(isinstance(item, dict) and _first_non_empty(item, "prices", "history") for item in list(raw_history)):
            for group in list(raw_history):
                store_name = cls._clean_text(
                    _first_non_empty(group, "store", "store_name", "merchant", "seller", "source")
                )
                group_points = _normalize_history_points(
                    _first_non_empty(group, "prices", "history", "price_history", "items") or [],
                    default_currency=str(currency or "").strip() or None,
                )
                for point in group_points:
                    point["store"] = store_name
                    point["label"] = point.get("label") or store_name
                    history.append(point)
                series.append({"store": store_name, "prices": group_points})
        else:
            history = _normalize_history_points(
                raw_history,
                default_currency=str(currency or "").strip() or None,
            )

        if latest_price is None and history:
            latest_price = history[-1]["price"]

        prices = [point["price"] for point in history if point.get("price") is not None]
        lowest_price = min(prices) if prices else latest_price
        highest_price = max(prices) if prices else latest_price

        return {
            "status": cls._normalize_status(payload),
            "message": cls._clean_text(payload.get("message") if isinstance(payload, dict) else None) or "",
            "product_id": provider_product_id,
            "country": country,
            "language": language,
            "provider_request_id": payload.get("request_id") if isinstance(payload, dict) else None,
            "title": cls._clean_text(title),
            "brand": cls._clean_text(brand),
            "latest_price": latest_price,
            "lowest_price": lowest_price,
            "highest_price": highest_price,
            "currency": str(currency or "").strip() or (history[0]["currency"] if history and history[0].get("currency") else None),
            "point_count": len(history),
            "history": history,
            "series": series,
            "source": cls.SOURCE_NAME,
        }

    @classmethod
    def _normalize_deals_payload(
        cls,
        payload: Dict,
        query: str,
        country: str,
        language: str,
        page: int,
        limit: int,
        sort_by: str,
        product_condition: str,
    ) -> Dict:
        data = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
        raw_items = []
        count = 0
        if isinstance(data, dict):
            raw_items = (
                _first_non_empty(data, "deals", "products", "results", "items", "shopping_results")
                or []
            )
            count = cls._extract_int(
                _first_non_empty(data, "total_deals", "total_products", "count", "total_count")
            ) or 0
        elif isinstance(data, list):
            raw_items = data

        deals = [item for item in (cls._normalize_product_item(entry) for entry in list(raw_items or [])) if item]
        return {
            "status": cls._normalize_status(payload),
            "message": cls._clean_text(payload.get("message") if isinstance(payload, dict) else None) or "",
            "query": query,
            "country": country,
            "language": language,
            "page": page,
            "limit": limit,
            "sort_by": sort_by,
            "product_condition": product_condition,
            "provider_request_id": payload.get("request_id") if isinstance(payload, dict) else None,
            "count": count or len(deals),
            "deals": deals,
            "source": cls.SOURCE_NAME,
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
