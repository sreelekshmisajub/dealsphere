from decimal import Decimal
import json
from pathlib import Path
from unittest.mock import patch

from django.test import Client, TestCase
from django.test import override_settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.api.ai_services import RealAIService
from apps.core.catalog_loader import CatalogBootstrapService
from apps.core.models import Brand, Category, Merchant, Offer, Order, Product
from apps.users.services import ProductService


User = get_user_model()


class _MockUrlOpenResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _mock_amazon_provider_response(request, timeout=None):
    request_url = getattr(request, "full_url", str(request))
    if "top-product-reviews" in request_url:
        return _MockUrlOpenResponse(
            {
                "status": "OK",
                "request_id": "req-review",
                "data": {
                    "asin": "B07ZPKBL9V",
                    "country": "US",
                    "domain": "www.amazon.com",
                    "rating_distribution": {"4": 2, "5": 8},
                    "reviews": [
                        {
                            "review_id": "R2",
                            "review_title": "Still worth buying",
                            "review_comment": "The performance is stable and the camera is dependable.",
                            "review_star_rating": "5",
                            "review_link": "https://www.amazon.com/gp/customer-reviews/R2",
                            "review_author": "Frontend QA",
                            "review_date": "Reviewed in the United States on March 24, 2026",
                            "is_verified_purchase": True,
                            "helpful_vote_statement": "One person found this helpful",
                            "review_images": [],
                        }
                    ],
                },
            }
        )
    return _MockUrlOpenResponse(
        {
            "title": "Apple iPhone 11 64GB Black",
            "brand": "Apple",
            "price": "$219.99",
            "list_price": "$249.99",
            "price_symbol": "$",
            "currency": "USD",
            "rating": "4.4",
            "ratings_total": "52581",
            "availability": "In Stock",
            "product_url": "https://www.amazon.com/dp/B07ZPKBL9V",
            "product_photo": "https://example.com/live-phone.jpg",
            "features": [
                "Unlocked smartphone",
                "Dual camera system",
                "All-day battery life",
            ],
            "sales_volume": "500+ bought in past month",
            "is_prime": True,
            "is_amazon_choice": False,
            "is_best_seller": False,
        }
    )


def _mock_female_footwear_response(request, timeout=None):
    return _MockUrlOpenResponse(
        {
            "value": [
                {
                    "Brand": "Campus",
                    "Description": "Lightweight running shoes for women",
                    "Image": "https://example.com/shoe.jpg",
                    "Price": "₹1,010",
                    "Tag": "Women",
                    "Unnamed: 0": 27,
                },
                {
                    "Brand": "Bata",
                    "Description": "Women Tan Flats Sandal",
                    "Image": "https://example.com/sandal.jpg",
                    "Price": "₹1,274",
                    "Tag": "Women",
                    "Unnamed: 0": 33,
                },
            ],
            "Count": 727,
        }
    )


TEST_REALTIME_PRODUCT_SEARCH_SETTINGS = {
    "host": "real-time-product-search.p.rapidapi.com",
    "key": "test-key",
    "search_endpoint": "https://real-time-product-search.p.rapidapi.com/search-v2",
    "product_details_endpoint": "https://real-time-product-search.p.rapidapi.com/product-details-v2",
    "product_offers_endpoint": "https://real-time-product-search.p.rapidapi.com/product-offers-v2",
    "product_price_history_endpoint": "https://real-time-product-search.p.rapidapi.com/product-price-history",
    "deals_endpoint": "https://real-time-product-search.p.rapidapi.com/deals-v2",
    "default_country": "in",
    "default_language": "en",
    "timeout_seconds": 12,
    "enabled": True,
}


def _mock_real_time_product_search_response(request, timeout=None):
    request_url = getattr(request, "full_url", str(request))

    if "search-v2" in request_url:
        return _MockUrlOpenResponse(
            {
                "status": "OK",
                "request_id": "req-search",
                "data": {
                    "total_products": 1,
                    "products": [
                        {
                            "product_id": "catalogid:shoe-1",
                            "product_title": "Nike Pegasus 40",
                            "brand": "Nike",
                            "product_page_url": "https://example.com/products/nike-pegasus-40",
                            "product_photo": "https://example.com/images/nike-pegasus-40.jpg",
                            "product_condition": "NEW",
                            "rating": "4.6",
                            "review_count": 128,
                            "badges": ["Best Match"],
                            "offer": {
                                "store_name": "Nike",
                                "price": "₹7,495",
                                "original_price": "₹8,995",
                                "currency": "INR",
                                "availability": "In stock",
                            },
                        }
                    ],
                    "filters": [
                        {
                            "key": "brand",
                            "label": "Brand",
                            "options": [
                                {"value": "Nike", "label": "Nike", "count": 10},
                            ],
                        }
                    ],
                },
            }
        )

    if "product-details-v2" in request_url:
        return _MockUrlOpenResponse(
            {
                "status": "OK",
                "request_id": "req-details",
                "data": {
                    "product_id": "catalogid:shoe-1",
                    "product_title": "Nike Pegasus 40",
                    "brand": "Nike",
                    "description": "Responsive running shoes for daily training.",
                    "product_page_url": "https://example.com/products/nike-pegasus-40",
                    "product_photos": [
                        "https://example.com/images/nike-pegasus-40.jpg",
                        "https://example.com/images/nike-pegasus-40-side.jpg",
                    ],
                    "rating": "4.6",
                    "review_count": 128,
                    "store_name": "Nike",
                    "availability": "In stock",
                    "product_condition": "NEW",
                    "offer": {
                        "price": "₹7,495",
                        "original_price": "₹8,995",
                        "currency": "INR",
                    },
                    "features": ["React foam midsole", "Breathable mesh upper"],
                    "specifications": {"Color": "Black/White", "Gender": "Men"},
                },
            }
        )

    if "product-offers-v2" in request_url:
        return _MockUrlOpenResponse(
            {
                "status": "OK",
                "request_id": "req-offers",
                "data": {
                    "product_id": "catalogid:shoe-1",
                    "product_title": "Nike Pegasus 40",
                    "offers": [
                        {
                            "store_name": "Nike",
                            "seller_name": "Nike Store",
                            "price": "₹7,495",
                            "original_price": "₹8,995",
                            "currency": "INR",
                            "availability": "In stock",
                            "shipping": "Free delivery",
                            "offer_page_url": "https://example.com/offers/nike-store",
                            "product_condition": "NEW",
                        },
                        {
                            "store_name": "Flipkart",
                            "seller_name": "Sportz",
                            "price": "₹7,299",
                            "original_price": "₹8,499",
                            "currency": "INR",
                            "availability": "Limited stock",
                            "shipping": "Delivery by tomorrow",
                            "offer_page_url": "https://example.com/offers/flipkart-sportz",
                            "product_condition": "NEW",
                        },
                    ],
                },
            }
        )

    if "product-price-history" in request_url:
        return _MockUrlOpenResponse(
            {
                "status": "OK",
                "request_id": "req-history",
                "data": {
                    "product_id": "catalogid:shoe-1",
                    "product_title": "Nike Pegasus 40",
                    "brand": "Nike",
                    "currency": "INR",
                    "price_history": [
                        {
                            "store": "Nike",
                            "prices": [
                                {"date": "2026-03-28", "price": "₹7,495"},
                                {"date": "2026-03-29", "price": "₹7,299"},
                            ],
                        },
                        {
                            "store": "Flipkart",
                            "prices": [
                                {"date": "2026-03-28", "price": "₹7,399"},
                            ],
                        },
                    ],
                },
            }
        )

    if "deals-v2" in request_url:
        return _MockUrlOpenResponse(
            {
                "status": "OK",
                "request_id": "req-deals",
                "data": {
                    "total_deals": 1,
                    "deals": [
                        {
                            "product_id": "deal-laptop-1",
                            "product_title": "Lenovo IdeaPad Gaming Laptop",
                            "brand": "Lenovo",
                            "product_page_url": "https://example.com/deals/lenovo-ideapad",
                            "product_photo": "https://example.com/images/lenovo-ideapad.jpg",
                            "product_condition": "NEW",
                            "rating": "4.4",
                            "review_count": 240,
                            "offer": {
                                "store_name": "Amazon",
                                "price": "₹59,990",
                                "original_price": "₹72,990",
                                "currency": "INR",
                                "availability": "In stock",
                            },
                        }
                    ],
                },
            }
        )

    raise AssertionError(f"Unexpected request URL for product search mock: {request_url}")


class FrontendSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogBootstrapService.ensure_loaded()

        cls.user = User.objects.create_user(
            username="frontend-user",
            email="frontend-user@example.com",
            password="CodexPass123!",
        )
        cls.merchant_user = User.objects.create_user(
            username="frontend-merchant",
            email="frontend-merchant@example.com",
            password="CodexPass123!",
            is_merchant=True,
        )
        cls.merchant = Merchant.objects.create(
            user=cls.merchant_user,
            shop_name="Frontend Merchant",
            address="Test City",
        )
        cls.category = Category.objects.filter(name__iexact="Electronics").first() or Category.objects.create(name="Electronics")
        cls.brand = Brand.objects.filter(name__iexact="Codex").first() or Brand.objects.create(name="Codex")
        cls.local_product = Product.objects.create(
            name="Codex Test Phone",
            category=cls.category,
            brand=cls.brand,
            amazon_price=Decimal("499.00"),
            amazon_url="https://www.amazon.com/dp/B07ZPKBL9V",
        )
        cls.flipkart_match_product = Product.objects.create(
            name="Codex Test Phone 5G",
            category=cls.category,
            brand=cls.brand,
            flipkart_price=Decimal("479.00"),
            flipkart_url="https://example.com/flipkart-phone",
        )
        cls.myntra_match_product = Product.objects.create(
            name="Codex Test Phone",
            category=cls.category,
            brand=cls.brand,
            myntra_price=Decimal("489.00"),
            myntra_url="https://example.com/myntra-phone",
        )
        Offer.objects.create(
            product=cls.local_product,
            merchant=cls.merchant,
            price=Decimal("450.00"),
            original_price=Decimal("499.00"),
            delivery_time_hours=4,
            stock_quantity=10,
            is_active=True,
        )
        cls.admin_user = User.objects.create_user(
            username="frontend-admin",
            email="frontend-admin@example.com",
            password="CodexPass123!",
            is_staff=True,
        )

    def test_public_pages_render(self):
        for route in ["/", "/deals/", "/price-alert/", "/price-history/", "/gift-cards/", "/login/", "/register/"]:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)

    def test_login_page_sets_fresh_csrf_cookie_and_accepts_post(self):
        client = Client(enforce_csrf_checks=True)
        login_page = client.get("/login/")
        self.assertEqual(login_page.status_code, 200)
        self.assertIn("csrftoken", login_page.cookies)
        self.assertIn("no-cache", login_page.headers.get("Cache-Control", ""))
        self.assertIn("no-store", login_page.headers.get("Cache-Control", ""))

        csrf_token = login_page.cookies["csrftoken"].value
        login_response = client.post(
            "/login/",
            {
                "email": "frontend-user@example.com",
                "password": "CodexPass123!",
                "csrfmiddlewaretoken": csrf_token,
            },
            HTTP_REFERER="http://127.0.0.1:8000/login/",
        )
        self.assertEqual(login_response.status_code, 302)
        search_response = self.client.get("/products/search/")
        self.assertGreater(search_response.context["total_count"], 0)

    def test_search_falls_back_to_real_catalog_when_query_has_no_exact_match(self):
        response = self.client.get("/products/search/?q=zzzznonexistentcatalogquery")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_count"], 0)
        self.assertIn("No real dataset match was found", response.context["fallback_message"])

    def test_search_applies_price_filter_without_query(self):
        response = self.client.get("/products/search/?max_price=99&sort_by=price_low")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.context["total_count"], 0)
        self.assertTrue(all(product.best_offer.price <= 99 for product in response.context["products"]))

    def test_search_applies_distinct_price_range(self):
        response = self.client.get("/products/search/?min_price=100&max_price=199&sort_by=price_low")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.context["total_count"], 0)
        self.assertTrue(all(100 <= product.best_offer.price <= 199 for product in response.context["products"]))

    def test_phone_search_prefers_phone_products_over_accessories(self):
        response = self.client.get("/products/search/?q=phone")
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.context["total_count"], 0)
        names = [product.name.lower() for product in response.context["products"]]
        self.assertTrue(any("smartphone" in name or "phone" in name or "mobile" in name for name in names))
        self.assertTrue(all("headphone" not in name and "cable" not in name for name in names))

    def test_product_detail_surfaces_related_marketplace_matches(self):
        candidates = ProductService.get_comparison_candidates(self.local_product.id)
        self.assertIn("amazon", {candidate["source"] for candidate in candidates})
        self.assertIn("flipkart", {candidate["source"] for candidate in candidates})
        self.assertIn("myntra", {candidate["source"] for candidate in candidates})

        self.client.login(username="frontend-user", password="CodexPass123!")
        response = self.client.get(f"/dashboard/product/{self.local_product.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Flipkart")
        self.assertContains(response, "Myntra")
        self.assertContains(response, "Related catalog match")
        self.assertContains(response, "https://example.com/myntra-phone")

    def test_product_detail_surfaces_related_local_match(self):
        target_product = Product.objects.create(
            name="Codex Compare Tablet",
            category=self.category,
            brand=self.brand,
            amazon_price=Decimal("799.00"),
            amazon_url="https://www.amazon.com/dp/B07TABLET99",
        )
        related_local_product = Product.objects.create(
            name="Codex Compare Tablet 5G",
            category=self.category,
            brand=self.brand,
        )
        Offer.objects.create(
            product=related_local_product,
            merchant=self.merchant,
            price=Decimal("749.00"),
            original_price=Decimal("799.00"),
            delivery_time_hours=5,
            stock_quantity=6,
            is_active=True,
        )

        candidates = ProductService.get_comparison_candidates(target_product.id)
        local_candidates = [candidate for candidate in candidates if candidate["source"] == "local"]
        self.assertTrue(local_candidates)
        self.assertEqual(local_candidates[0]["match_type"], "catalog_match")

        self.client.login(username="frontend-user", password="CodexPass123!")
        response = self.client.get(f"/dashboard/product/{target_product.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Local Shops")
        self.assertContains(response, "Frontend Merchant")
        self.assertContains(response, "related catalog row")

    def test_product_detail_collapses_missing_sources_into_single_note(self):
        isolated_product = Product.objects.create(
            name="ZXQP Isolated Alpha Omega Device",
            amazon_price=Decimal("299.00"),
            amazon_url="https://www.amazon.com/dp/B07ISOLATED9",
        )

        self.client.login(username="frontend-user", password="CodexPass123!")
        response = self.client.get(f"/dashboard/product/{isolated_product.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Other sources not shown")
        self.assertNotContains(
            response,
            "No comparable Flipkart row is currently attached or matched in the loaded catalog.",
        )
        self.assertNotContains(
            response,
            "No comparable Myntra row is currently attached or matched in the loaded catalog.",
        )
        self.assertNotContains(
            response,
            "No active local merchant offer is attached to this product.",
        )

    def test_user_frontend_pages_render(self):
        self.client.login(username="frontend-user", password="CodexPass123!")
        for route in [
            "/dashboard/",
            "/dashboard/results/",
            "/dashboard/barcode/",
            "/dashboard/visual-search/",
            "/dashboard/basket/",
            "/dashboard/deal-lock/",
            "/dashboard/notifications/",
            "/dashboard/profile/",
            "/cart/",
            "/notifications/",
            "/profile/",
        ]:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)

    @patch("dealsphere.site_views.RealAIService.identify_product")
    def test_visual_search_dashboard_page_processes_uploaded_image(self, mock_identify):
        mock_identify.return_value = {
            "status": "ok",
            "predicted_category": "smartphone",
            "predicted_supercategory": "electronics",
            "confidence": 0.84,
            "all_predictions": [
                {
                    "predicted_category": "smartphone",
                    "predicted_supercategory": "electronics",
                    "confidence": 0.84,
                    "supporting_matches": 3,
                }
            ],
            "matching_products": [self.local_product],
            "reference_matches": [
                {
                    "category_name": "smartphone",
                    "supercategory": "electronics",
                    "similarity": 0.84,
                    "reference_image": "sample_phone.jpg",
                }
            ],
            "dataset_reference_images": 24,
        }

        self.client.login(username="frontend-user", password="CodexPass123!")
        response = self.client.post(
            "/dashboard/visual-search/",
            {
                "image": SimpleUploadedFile("phone.jpg", b"fake-image-bytes", content_type="image/jpeg"),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "smartphone")
        self.assertContains(response, "Electronics")
        self.assertContains(response, "Codex Test Phone")
        self.assertContains(response, "sample_phone.jpg")
        self.assertContains(response, "Open Product")

    def test_user_can_update_profile_from_dashboard(self):
        self.client.login(username="frontend-user", password="CodexPass123!")
        response = self.client.post(
            "/dashboard/profile/",
            {
                "first_name": "Updated",
                "last_name": "User",
                "email": "frontend-user@example.com",
                "phone": "9876543210",
                "location_lat": "10.12345678",
                "location_lng": "76.12345678",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/profile/")

        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Updated")
        self.assertEqual(self.user.phone, "9876543210")

    def test_basket_optimizes_against_exact_cart_product(self):
        misleading_product = Product.objects.create(
            name="Codex Basket Match Pro",
            category=self.category,
            brand=self.brand,
            amazon_price=Decimal("999.00"),
        )
        target_product = Product.objects.create(
            name="Codex Basket Match",
            category=self.category,
            brand=self.brand,
            amazon_price=Decimal("310.00"),
        )
        Offer.objects.create(
            product=target_product,
            merchant=self.merchant,
            price=Decimal("260.00"),
            original_price=Decimal("310.00"),
            delivery_time_hours=3,
            stock_quantity=5,
            is_active=True,
        )

        self.client.login(username="frontend-user", password="CodexPass123!")
        add_response = self.client.post(
            "/dashboard/cart/add/",
            {
                "product_id": target_product.id,
                "quantity": 1,
                "source": "amazon",
                "next": "/dashboard/basket/",
            },
        )
        self.assertEqual(add_response.status_code, 302)

        response = self.client.get("/dashboard/basket/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["optimization"]["best_option"]["items"][0]["product_id"], target_product.id)
        self.assertEqual(response.context["optimized_total"], 260.0)
        self.assertEqual(response.context["current_cart_savings"], 50.0)
        self.assertNotEqual(misleading_product.id, response.context["optimization"]["best_option"]["items"][0]["product_id"])

    def test_myntra_only_checkout_uses_external_redirect(self):
        self.client.login(username="frontend-user", password="CodexPass123!")
        add_response = self.client.post(
            "/dashboard/cart/add/",
            {
                "product_id": self.myntra_match_product.id,
                "quantity": 1,
                "source": "myntra",
                "next": "/dashboard/basket/",
            },
        )
        self.assertEqual(add_response.status_code, 302)

        basket_response = self.client.get("/dashboard/basket/")
        self.assertEqual(basket_response.status_code, 200)
        self.assertFalse(basket_response.context["basket_checkout_blocked"])

        checkout_response = self.client.get("/dashboard/checkout/")
        self.assertEqual(checkout_response.status_code, 200)
        self.assertTrue(checkout_response.context["has_external_items"])
        self.assertFalse(checkout_response.context["has_local_items"])
        self.assertEqual(len(checkout_response.context["payment_choices"]), 1)
        self.assertEqual(checkout_response.context["payment_choices"][0].value, "external_redirect")

    def test_dashboard_checkout_creates_real_order(self):
        self.client.login(username="frontend-user", password="CodexPass123!")
        add_response = self.client.post(
            "/dashboard/cart/add/",
            {
                "product_id": self.local_product.id,
                "quantity": 2,
                "source": "local",
                "merchant_id": self.merchant.id,
                "next": "/dashboard/results/",
            },
        )
        self.assertEqual(add_response.status_code, 302)

        checkout_response = self.client.post(
            "/dashboard/checkout/",
            {
                "delivery_address": "Test Checkout Address",
                "payment_method": "cash_on_delivery",
            },
        )
        self.assertEqual(checkout_response.status_code, 200)

        order = Order.objects.filter(user=self.user).latest("created_at")
        self.assertEqual(order.payment_method, "cash_on_delivery")
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.items.first().merchant, self.merchant)
        self.assertEqual(order.items.first().source, "local")

    @override_settings(
        PAYMENT_SETTINGS={
            "upi_id": "dealsphere@upi",
            "upi_name": "DealSphere",
            "gateway_url": "",
            "gateway_name": "Online Gateway",
            "upi_enabled": True,
            "gateway_enabled": False,
        }
    )
    def test_upi_checkout_generates_payment_link(self):
        self.client.login(username="frontend-user", password="CodexPass123!")
        self.client.post(
            "/dashboard/cart/add/",
            {
                "product_id": self.local_product.id,
                "quantity": 1,
                "source": "local",
                "merchant_id": self.merchant.id,
                "next": "/dashboard/basket/",
            },
        )
        response = self.client.post(
            "/dashboard/checkout/",
            {
                "delivery_address": "UPI Address",
                "payment_method": "upi",
            },
        )
        self.assertEqual(response.status_code, 200)
        order = Order.objects.filter(user=self.user).latest("created_at")
        self.assertEqual(order.payment_method, "upi")
        self.assertEqual(order.payment_status, "redirect_required")
        self.assertTrue(order.payment_link.startswith("upi://pay?"))

    def test_merchant_and_admin_dashboards_render(self):
        self.client.login(username="frontend-merchant", password="CodexPass123!")
        for route in [
            "/dashboard/merchant/",
            "/dashboard/merchant/products/",
            "/dashboard/merchant/products/add/",
            "/dashboard/merchant/requests/",
            "/dashboard/merchant/deals/",
            "/dashboard/merchant/delivery/",
            "/dashboard/merchant/analytics/",
            "/dashboard/merchant/notifications/",
            "/dashboard/merchant/profile/",
        ]:
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route).status_code, 200)
        legacy_response = self.client.get("/merchant/dashboard/")
        self.assertEqual(legacy_response.status_code, 302)
        self.assertEqual(legacy_response.url, "/dashboard/merchant/")

        self.client.logout()
        self.client.login(username="frontend-admin", password="CodexPass123!")
        self.assertEqual(self.client.get("/dashboard/admin/").status_code, 200)
        legacy_response = self.client.get("/admin/dashboard/")
        self.assertEqual(legacy_response.status_code, 302)
        self.assertEqual(legacy_response.url, "/dashboard/admin/")

    def test_external_barcode_lookup_uses_dataset(self):
        result = RealAIService.barcode_search("00000092")
        self.assertTrue(result["found"])
        self.assertEqual(result["match_type"], "external_dataset")

    def test_sparse_history_price_prediction_returns_fallback_forecast(self):
        sparse_product = Product.objects.create(
            name="Sparse History Product",
            category=self.category,
            brand=self.brand,
            amazon_price=Decimal("299.00"),
            amazon_url="https://example.com/sparse-history",
        )
        prediction = RealAIService.predict_price(sparse_product.id, 5)
        self.assertEqual(prediction["status"], "heuristic_fallback")
        self.assertEqual(len(prediction["predictions"]), 5)
        self.assertIn("fallback_basis", prediction)

    def test_visual_search_endpoint_uses_local_dataset(self):
        dataset_dir = Path(__file__).resolve().parents[2] / "dataset" / "retail_product_checkout" / "val2019"
        sample_image_path = next(dataset_dir.glob("*.jpg"))
        self.client.login(username="frontend-user", password="CodexPass123!")
        with sample_image_path.open("rb") as image_handle:
            response = self.client.post(
                "/api/v1/ai/identify/",
                {"image": SimpleUploadedFile(sample_image_path.name, image_handle.read(), content_type="image/jpeg")},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertTrue(response.json()["predicted_supercategory"])

    def test_ai_engine_wrapper_is_mounted(self):
        response = self.client.get("/api/v1/ai-engine/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "healthy")

    @override_settings(
        AMAZON_REVIEW_API_SETTINGS={
            "endpoint": "https://real-time-amazon-data.p.rapidapi.com/top-product-reviews",
            "host": "real-time-amazon-data.p.rapidapi.com",
            "key": "test-key",
            "default_country": "US",
            "timeout_seconds": 5,
            "enabled": True,
        }
    )
    @patch("apps.api.ai_services.urlopen")
    def test_amazon_reviews_api_returns_normalized_live_shape(self, mock_urlopen):
        mock_urlopen.return_value = _MockUrlOpenResponse(
            {
                "status": "OK",
                "request_id": "req-123",
                "data": {
                    "asin": "B07ZPKBL9V",
                    "country": "US",
                    "domain": "www.amazon.com",
                    "rating_distribution": {"1": 1, "5": 9},
                    "reviews": [
                        {
                            "review_id": "R1",
                            "review_title": "Excellent phone",
                            "review_comment": "Battery life is solid and delivery was quick.",
                            "review_star_rating": "5",
                            "review_link": "https://www.amazon.com/gp/customer-reviews/R1",
                            "review_author": "Codex Tester",
                            "review_author_avatar": "https://example.com/avatar.jpg",
                            "review_date": "Reviewed in the United States on March 24, 2026",
                            "is_verified_purchase": True,
                            "helpful_vote_statement": "2 people found this helpful",
                            "review_images": ["https://example.com/review.jpg"],
                        }
                    ],
                },
            }
        )

        self.client.login(username="frontend-user", password="CodexPass123!")
        response = self.client.get(f"/api/v1/products/{self.local_product.id}/amazon-reviews/?limit=1")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["asin"], "B07ZPKBL9V")
        self.assertEqual(payload["review_count"], 1)
        self.assertEqual(payload["reviews"][0]["review_title"], "Excellent phone")

    @override_settings(
        ENABLE_LIVE_PRODUCT_PAGE_ENRICHMENT=True,
        AMAZON_REVIEW_API_SETTINGS={
            "endpoint": "https://real-time-amazon-data.p.rapidapi.com/top-product-reviews",
            "host": "real-time-amazon-data.p.rapidapi.com",
            "key": "test-key",
            "default_country": "US",
            "timeout_seconds": 5,
            "enabled": True,
        }
    )
    @patch("apps.api.ai_services.urlopen")
    def test_dashboard_product_page_renders_live_amazon_reviews(self, mock_urlopen):
        mock_urlopen.side_effect = _mock_amazon_provider_response

        self.client.login(username="frontend-user", password="CodexPass123!")
        response = self.client.get(f"/dashboard/product/{self.local_product.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Live Amazon Reviews")
        self.assertContains(response, "Still worth buying")

    @override_settings(
        AMAZON_PRODUCT_INFO_API_SETTINGS={
            "endpoint": "https://amazon-pricing-and-product-info.p.rapidapi.com/",
            "host": "amazon-pricing-and-product-info.p.rapidapi.com",
            "key": "test-key",
            "default_domain": "com",
            "timeout_seconds": 5,
            "enabled": True,
        }
    )
    @patch("apps.api.ai_services.urlopen")
    def test_amazon_snapshot_api_returns_normalized_live_shape(self, mock_urlopen):
        mock_urlopen.side_effect = _mock_amazon_provider_response

        self.client.login(username="frontend-user", password="CodexPass123!")
        response = self.client.get(f"/api/v1/products/{self.local_product.id}/amazon-snapshot/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["asin"], "B07ZPKBL9V")
        self.assertEqual(payload["live_title"], "Apple iPhone 11 64GB Black")
        self.assertEqual(payload["current_price"], 219.99)

    @override_settings(
        ENABLE_LIVE_PRODUCT_PAGE_ENRICHMENT=True,
        AMAZON_PRODUCT_INFO_API_SETTINGS={
            "endpoint": "https://amazon-pricing-and-product-info.p.rapidapi.com/",
            "host": "amazon-pricing-and-product-info.p.rapidapi.com",
            "key": "test-key",
            "default_domain": "com",
            "timeout_seconds": 5,
            "enabled": True,
        }
    )
    @patch("apps.api.ai_services.urlopen")
    def test_dashboard_product_page_renders_live_amazon_snapshot(self, mock_urlopen):
        mock_urlopen.side_effect = _mock_amazon_provider_response

        self.client.login(username="frontend-user", password="CodexPass123!")
        response = self.client.get(f"/dashboard/product/{self.local_product.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Live Amazon Snapshot")
        self.assertContains(response, "Apple iPhone 11 64GB Black")

    @patch("dealsphere.site_views.RealAIService.get_amazon_reviews", side_effect=AssertionError("reviews should not load"))
    @patch("dealsphere.site_views.RealAIService.get_amazon_product_snapshot", side_effect=AssertionError("snapshot should not load"))
    @patch("dealsphere.site_views.RealTimePriceService.fetch_live_prices", side_effect=AssertionError("live prices should not load"))
    def test_dashboard_product_page_skips_live_enrichment_by_default(
        self,
        mock_live_prices,
        mock_snapshot,
        mock_reviews,
    ):
        self.client.login(username="frontend-user", password="CodexPass123!")
        response = self.client.get(f"/dashboard/product/{self.local_product.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Live Amazon Snapshot")
        self.assertNotContains(response, "Live Retail Prices")

    @patch("apps.api.external_feeds.ExternalFashionFeedService.get_female_footwear", side_effect=AssertionError("external feed should not load"))
    def test_public_search_trending_skips_external_feed_by_default(self, mock_feed):
        response = self.client.get("/products/search/")
        self.assertEqual(response.status_code, 200)

    @patch("apps.api.external_feeds.urlopen")
    def test_external_female_footwear_feed_is_normalized(self, mock_urlopen):
        mock_urlopen.side_effect = _mock_female_footwear_response

        self.client.login(username="frontend-user", password="CodexPass123!")
        response = self.client.get("/api/v1/external/female-footwear/?limit=2")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["count"], 727)
        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual(payload["items"][0]["brand"], "Campus")
        self.assertEqual(payload["items"][0]["price_value"], 1010.0)

    @override_settings(REALTIME_PRODUCT_SEARCH_API_SETTINGS=TEST_REALTIME_PRODUCT_SEARCH_SETTINGS)
    @patch("apps.api.external_feeds.urlopen")
    def test_external_product_search_is_normalized(self, mock_urlopen):
        mock_urlopen.side_effect = _mock_real_time_product_search_response

        self.client.login(username="frontend-user", password="CodexPass123!")
        response = self.client.get(
            "/api/v1/external/product-search/?q=Nike%20shoes&country=in&language=en&page=1&limit=10&sort_by=BEST_MATCH&product_condition=ANY&return_filters=true"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["products"][0]["title"], "Nike Pegasus 40")
        self.assertEqual(payload["products"][0]["current_price"], 7495.0)
        self.assertEqual(payload["filters"][0]["key"], "brand")

    @override_settings(REALTIME_PRODUCT_SEARCH_API_SETTINGS=TEST_REALTIME_PRODUCT_SEARCH_SETTINGS)
    @patch("apps.api.external_feeds.urlopen")
    def test_external_product_details_is_normalized(self, mock_urlopen):
        mock_urlopen.side_effect = _mock_real_time_product_search_response

        self.client.login(username="frontend-user", password="CodexPass123!")
        response = self.client.get(
            "/api/v1/external/product-details/?product_id=catalogid%3Ashoe-1&country=in&language=en"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["brand"], "Nike")
        self.assertEqual(payload["current_price"], 7495.0)
        self.assertEqual(len(payload["images"]), 2)
        self.assertEqual(payload["features"][0], "React foam midsole")

    @override_settings(REALTIME_PRODUCT_SEARCH_API_SETTINGS=TEST_REALTIME_PRODUCT_SEARCH_SETTINGS)
    @patch("apps.api.external_feeds.urlopen")
    def test_external_product_offers_is_normalized(self, mock_urlopen):
        mock_urlopen.side_effect = _mock_real_time_product_search_response

        self.client.login(username="frontend-user", password="CodexPass123!")
        response = self.client.get(
            "/api/v1/external/product-offers/?product_id=catalogid%3Ashoe-1&page=1&country=in&language=en"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["offers_count"], 2)
        self.assertEqual(payload["offers"][1]["store"], "Flipkart")
        self.assertEqual(payload["offers"][1]["current_price"], 7299.0)

    @override_settings(REALTIME_PRODUCT_SEARCH_API_SETTINGS=TEST_REALTIME_PRODUCT_SEARCH_SETTINGS)
    @patch("apps.api.external_feeds.urlopen")
    def test_external_product_price_history_flattens_store_series(self, mock_urlopen):
        mock_urlopen.side_effect = _mock_real_time_product_search_response

        self.client.login(username="frontend-user", password="CodexPass123!")
        response = self.client.get(
            "/api/v1/external/product-price-history/?product_id=catalogid%3Ashoe-1&country=in&language=en"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["point_count"], 3)
        self.assertEqual(len(payload["series"]), 2)
        self.assertEqual(payload["series"][0]["store"], "Nike")
        self.assertEqual(payload["history"][0]["store"], "Nike")
        self.assertEqual(payload["lowest_price"], 7299.0)

    @override_settings(REALTIME_PRODUCT_SEARCH_API_SETTINGS=TEST_REALTIME_PRODUCT_SEARCH_SETTINGS)
    @patch("apps.api.external_feeds.urlopen")
    def test_external_deals_is_normalized(self, mock_urlopen):
        mock_urlopen.side_effect = _mock_real_time_product_search_response

        self.client.login(username="frontend-user", password="CodexPass123!")
        response = self.client.get(
            "/api/v1/external/deals/?q=Laptop&country=in&language=en&page=1&limit=10&sort_by=BEST_MATCH&product_condition=ANY"
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["deals"][0]["brand"], "Lenovo")
        self.assertEqual(payload["deals"][0]["current_price"], 59990.0)

    def test_frontend_registration_redirects_to_login_without_auto_login(self):
        response = self.client.post(
            "/register/",
            {
                "user_type": "customer",
                "first_name": "Flow",
                "last_name": "User",
                "email": "flow-user@example.com",
                "phone": "9876543210",
                "password": "FlowPass123!",
                "confirm_password": "FlowPass123!",
                "location_lat": "10.12345678",
                "location_lng": "76.12345678",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/login/")
        self.assertTrue(User.objects.filter(email="flow-user@example.com").exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_frontend_merchant_registration_redirects_to_login(self):
        response = self.client.post(
            "/register/",
            {
                "user_type": "merchant",
                "first_name": "Shop",
                "last_name": "Owner",
                "email": "shop-owner@example.com",
                "phone": "9876543211",
                "password": "ShopPass123!",
                "confirm_password": "ShopPass123!",
                "location_lat": "10.22345678",
                "location_lng": "76.22345678",
                "shop_name": "Local Verified Mart",
                "business_category": "Groceries",
                "address": "Test Merchant Street",
                "delivery_enabled": "on",
                "delivery_radius_km": "8",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/login/")
        merchant_user = User.objects.get(email="shop-owner@example.com")
        self.assertTrue(merchant_user.is_merchant)
        self.assertEqual(merchant_user.merchant_profile.business_category, "Groceries")
        self.assertTrue(merchant_user.merchant_profile.delivery_enabled)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_redirects_by_role(self):
        response = self.client.post(
            "/login/",
            {"email": "frontend-user@example.com", "password": "CodexPass123!"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/")

        self.client.logout()
        response = self.client.post(
            "/login/",
            {"email": "frontend-merchant@example.com", "password": "CodexPass123!"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/merchant/")

        self.client.logout()
        response = self.client.post(
            "/login/",
            {"email": "frontend-admin@example.com", "password": "CodexPass123!"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/dashboard/admin/")

    def test_customer_pages_reject_merchant(self):
        self.client.login(username="frontend-merchant", password="CodexPass123!")
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")


class WorkflowApiSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        CatalogBootstrapService.ensure_loaded()
        cls.user = User.objects.create_user(
            username="api-user",
            email="api-user@example.com",
            password="ApiPass123!",
        )
        cls.merchant_user = User.objects.create_user(
            username="api-merchant",
            email="api-merchant@example.com",
            password="ApiPass123!",
            is_merchant=True,
        )
        Merchant.objects.create(
            user=cls.merchant_user,
            shop_name="API Merchant",
            business_category="Electronics",
            address="API Street",
        )
        cls.admin_user = User.objects.create_user(
            username="api-admin",
            email="api-admin@example.com",
            password="ApiPass123!",
            is_staff=True,
        )

    def setUp(self):
        self.api_client = APIClient()

    def test_api_user_registration_returns_message_without_tokens(self):
        response = self.api_client.post(
            "/api/v1/auth/register/",
            {
                "first_name": "Api",
                "last_name": "Flow",
                "email": "new-api-user@example.com",
                "phone": "9876543212",
                "password": "ApiFlow123!",
                "confirm_password": "ApiFlow123!",
                "location_lat": "9.92345678",
                "location_lng": "76.92345678",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("message", response.data)
        self.assertNotIn("tokens", response.data)

    def test_admin_api_blocks_non_admin_user(self):
        self.api_client.login(username="api-user", password="ApiPass123!")
        response = self.api_client.get("/api/v1/admin/dashboard/")
        self.assertEqual(response.status_code, 403)

        self.api_client.logout()
        self.api_client.login(username="api-admin", password="ApiPass123!")
        response = self.api_client.get("/api/v1/admin/dashboard/")
        self.assertEqual(response.status_code, 200)

    def test_merchant_api_blocks_non_merchant_user(self):
        self.api_client.login(username="api-user", password="ApiPass123!")
        response = self.api_client.get("/api/v1/merchants/offers/")
        self.assertEqual(response.status_code, 403)

        self.api_client.logout()
        self.api_client.login(username="api-merchant", password="ApiPass123!")
        response = self.api_client.get("/api/v1/merchants/offers/")
        self.assertEqual(response.status_code, 200)

    def test_merchant_api_add_product_creates_searchable_offer(self):
        merchant = Merchant.objects.get(user=self.merchant_user)
        category = Category.objects.filter(name__iexact="Electronics").first() or Category.objects.create(name="Electronics")

        self.api_client.login(username="api-merchant", password="ApiPass123!")
        response = self.api_client.post(
            "/api/v1/merchants/products/add/",
            {
                "name": "Merchant API Visible Phone",
                "category": category.id,
                "description": "A merchant-listed phone",
                "price": "649.00",
                "original_price": "699.00",
                "stock_quantity": 7,
                "delivery_time_hours": 4,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["listing_visible"])

        product = Product.objects.get(name="Merchant API Visible Phone")
        offer = Offer.objects.get(product=product, merchant=merchant)
        self.assertTrue(offer.is_active)
        self.assertEqual(offer.price, Decimal("649.00"))

        self.api_client.logout()
        self.api_client.login(username="api-user", password="ApiPass123!")
        search_response = self.api_client.get("/api/v1/users/search/?q=Merchant API Visible Phone")
        self.assertEqual(search_response.status_code, 200)
        self.assertTrue(any(item["id"] == product.id for item in search_response.data))

    def test_order_flow_is_visible_to_merchant_and_admin_apis(self):
        category = Category.objects.filter(name__iexact="Electronics").first() or Category.objects.create(name="Electronics")
        product = Product.objects.create(
            name="API Order Phone",
            category=category,
            amazon_price=Decimal("799.00"),
            amazon_url="https://example.com/api-order-phone",
        )
        merchant = Merchant.objects.get(user=self.merchant_user)
        Offer.objects.create(
            product=product,
            merchant=merchant,
            price=Decimal("699.00"),
            original_price=Decimal("799.00"),
            delivery_time_hours=3,
            stock_quantity=5,
            is_active=True,
        )

        self.api_client.login(username="api-user", password="ApiPass123!")
        add_response = self.api_client.post(
            "/api/v1/users/cart/add/",
            {
                "product_id": product.id,
                "quantity": 1,
                "source": "local",
                "merchant_id": merchant.id,
            },
            format="json",
        )
        self.assertEqual(add_response.status_code, 201)
        checkout_response = self.api_client.post(
            "/api/v1/users/checkout/",
            {
                "delivery_address": "API Checkout Street",
                "payment_method": "cash_on_delivery",
            },
            format="json",
        )
        self.assertEqual(checkout_response.status_code, 201)

        self.api_client.logout()
        self.api_client.login(username="api-merchant", password="ApiPass123!")
        merchant_orders = self.api_client.get("/api/v1/merchants/orders/")
        self.assertEqual(merchant_orders.status_code, 200)
        self.assertGreaterEqual(len(merchant_orders.data), 1)

        self.api_client.logout()
        self.api_client.login(username="api-admin", password="ApiPass123!")
        admin_orders = self.api_client.get("/api/v1/admin/orders/")
        self.assertEqual(admin_orders.status_code, 200)
        self.assertGreaterEqual(len(admin_orders.data), 1)
