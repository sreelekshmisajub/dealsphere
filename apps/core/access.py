from rest_framework.permissions import BasePermission


class IsAdminUser(BasePermission):
    message = "Admin access is required for this action."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and user.is_staff)


class IsMerchantUser(BasePermission):
    message = "Merchant access is required for this action."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and user.is_merchant and hasattr(user, "merchant_profile"))


class IsCustomerUser(BasePermission):
    message = "Customer access is required for this action."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        return bool(user and user.is_authenticated and not user.is_staff and not user.is_merchant)
