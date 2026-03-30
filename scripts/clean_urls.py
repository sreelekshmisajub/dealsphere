import os
import django
import re
from typing import Optional

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dealsphere.settings')
django.setup()

from apps.core.models import Product

def first_image(value) -> Optional[str]:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return None
    url = text.split("|")[0].strip()

    # Clean Amazon/Flipkart image URLs
    if url.endswith("webp_"):
        url = url[:-5] + "webp"

    # Handle various Amazon URL patterns
    amazon_match = re.search(r"(https://m\.media-amazon\.com/images/.*?[^._]+)(\._.*)(\.jpg|\.png|\.webp)$", url)
    if amazon_match:
        url = amazon_match.group(1) + amazon_match.group(3)

    return url

def main():
    products = Product.objects.all()
    updated = 0
    for p in products:
        cleaned = first_image(p.image_url)
        if cleaned != p.image_url:
            p.image_url = cleaned
            p.save()
            updated += 1
    print(f"Updated {updated} products")

if __name__ == "__main__":
    main()
