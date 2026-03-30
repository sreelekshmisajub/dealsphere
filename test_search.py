import os
import django
import pandas as pd
import numpy as np

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dealsphere.settings')
django.setup()

from apps.ai_engine.integrations import ai_integration

print("Searching for 'Apple'...")
results = ai_integration.search_in_datasets('Apple')
print(f"Found {len(results)} results")

for res in results[:3]:
    print(f"- {res['name']} | ₹{res['best_offer']['price']} | {res['source']}")

print("\nSearching for 'Headphones'...")
results = ai_integration.search_in_datasets('Headphones')
print(f"Found {len(results)} results")
for res in results[:3]:
    print(f"- {res['name']} | ₹{res['best_offer']['price']} | {res['source']}")
