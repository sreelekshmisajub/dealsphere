from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify

from apps.core.models import Cart, Merchant, UserActivity
from utils.validators import (
    validate_gstin,
    validate_location,
    validate_phone_number,
    validate_strong_password,
)


User = get_user_model()


def _clean_required_text(data, field_name: str, label: str) -> str:
    value = str(data.get(field_name, "") or "").strip()
    if not value:
        raise ValidationError(f"{label} is required.")
    return value


def _clean_optional_text(data, field_name: str) -> str | None:
    value = str(data.get(field_name, "") or "").strip()
    return value or None


def _clean_email(data) -> str:
    email = _clean_required_text(data, "email", "Email").lower()
    if User.objects.filter(email__iexact=email).exists():
        raise ValidationError("An account with that email already exists.")
    return email


def _clean_phone(data) -> str:
    phone = _clean_required_text(data, "phone", "Phone number")
    return validate_phone_number(phone)


def _clean_password(data) -> str:
    password = str(data.get("password", "") or "")
    confirm_password = str(data.get("confirm_password", "") or "")
    if not password:
        raise ValidationError("Password is required.")
    if password != confirm_password:
        raise ValidationError("Passwords do not match.")
    validate_strong_password(password)
    validate_password(password)
    return password


def _clean_coordinates(data, required: bool = True) -> tuple[str | None, str | None]:
    lat = data.get("location_lat")
    lng = data.get("location_lng")
    if required and (lat in (None, "") or lng in (None, "")):
        raise ValidationError("Location coordinates are required.")
    if lat in (None, "") and lng in (None, ""):
        return None, None
    validate_location(lat, lng)
    return str(lat), str(lng)


def _clean_delivery_radius(data) -> int:
    raw_radius = data.get("delivery_radius_km", 0)
    if raw_radius in (None, ""):
        return 0
    try:
        radius = int(raw_radius)
    except (TypeError, ValueError):
        raise ValidationError("Delivery radius must be a whole number.")
    if radius < 0:
        raise ValidationError("Delivery radius cannot be negative.")
    if radius > 100:
        raise ValidationError("Delivery radius cannot exceed 100 km.")
    return radius


def _clean_boolean(data, field_name: str) -> bool:
    value = data.get(field_name)
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def build_unique_username(*, email: str, first_name: str = "", last_name: str = "", prefix: str = "user") -> str:
    base_candidates = [
        slugify(f"{first_name} {last_name}"),
        slugify(email.split("@")[0]),
        prefix,
    ]
    base = next((candidate for candidate in base_candidates if candidate), prefix)
    base = base[:140]
    username = base
    suffix = 1

    while User.objects.filter(username__iexact=username).exists():
        suffix += 1
        username = f"{base[:140]}-{suffix}"[:150]

    return username


def validate_customer_registration_data(data):
    first_name = _clean_required_text(data, "first_name", "First name")
    last_name = _clean_required_text(data, "last_name", "Last name")
    email = _clean_email(data)
    phone = _clean_phone(data)
    password = _clean_password(data)
    location_lat, location_lng = _clean_coordinates(data, required=True)

    return {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "password": password,
        "location_lat": location_lat,
        "location_lng": location_lng,
    }


@transaction.atomic
def create_customer_account(data, *, activity_source: str):
    cleaned = validate_customer_registration_data(data)

    user = User.objects.create_user(
        username=build_unique_username(
            email=cleaned["email"],
            first_name=cleaned["first_name"],
            last_name=cleaned["last_name"],
            prefix="user",
        ),
        email=cleaned["email"],
        first_name=cleaned["first_name"],
        last_name=cleaned["last_name"],
        phone=cleaned["phone"],
        password=cleaned["password"],
        location_lat=cleaned["location_lat"],
        location_lng=cleaned["location_lng"],
    )
    Cart.objects.get_or_create(user=user)
    UserActivity.objects.create(
        user=user,
        activity_type="user_registered",
        metadata={"registration_method": activity_source, "merchant_mode": False},
    )
    return user


def validate_merchant_registration_data(data):
    first_name = _clean_required_text(data, "first_name", "Owner first name")
    last_name = _clean_required_text(data, "last_name", "Owner last name")
    email = _clean_email(data)
    phone = _clean_phone(data)
    password = _clean_password(data)
    shop_name = _clean_required_text(data, "shop_name", "Shop name")
    address = _clean_required_text(data, "address", "Business address")
    business_category = _clean_required_text(data, "business_category", "Business category")
    location_lat, location_lng = _clean_coordinates(data, required=True)
    gstin = _clean_optional_text(data, "gstin")
    if gstin:
        gstin = validate_gstin(gstin)

    delivery_enabled = _clean_boolean(data, "delivery_enabled")
    delivery_radius_km = _clean_delivery_radius(data)
    if delivery_enabled and delivery_radius_km == 0:
        raise ValidationError("Delivery radius is required when hyperlocal delivery is enabled.")

    return {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "password": password,
        "shop_name": shop_name,
        "address": address,
        "business_category": business_category,
        "location_lat": location_lat,
        "location_lng": location_lng,
        "gstin": gstin,
        "delivery_enabled": delivery_enabled,
        "delivery_radius_km": delivery_radius_km,
    }


@transaction.atomic
def create_merchant_account(data, *, activity_source: str):
    cleaned = validate_merchant_registration_data(data)

    user = User.objects.create_user(
        username=build_unique_username(
            email=cleaned["email"],
            first_name=cleaned["first_name"],
            last_name=cleaned["last_name"],
            prefix="merchant",
        ),
        email=cleaned["email"],
        first_name=cleaned["first_name"],
        last_name=cleaned["last_name"],
        phone=cleaned["phone"],
        password=cleaned["password"],
        is_merchant=True,
        location_lat=cleaned["location_lat"],
        location_lng=cleaned["location_lng"],
    )
    Cart.objects.get_or_create(user=user)
    Merchant.objects.create(
        user=user,
        shop_name=cleaned["shop_name"],
        gstin=cleaned["gstin"],
        location_lat=cleaned["location_lat"],
        location_lng=cleaned["location_lng"],
        address=cleaned["address"],
        business_category=cleaned["business_category"],
        delivery_enabled=cleaned["delivery_enabled"],
        delivery_radius_km=cleaned["delivery_radius_km"],
        verified=False,
    )
    UserActivity.objects.create(
        user=user,
        activity_type="user_registered",
        metadata={"registration_method": activity_source, "merchant_mode": True},
    )
    return user
