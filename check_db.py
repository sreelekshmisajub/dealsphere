import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dealsphere.settings')
django.setup()

from apps.core.models import Product, Offer, Category
print(f"Products: {Product.objects.count()}")
print(f"Offers: {Offer.objects.count()}")
print(f"Categories: {Category.objects.count()}")
