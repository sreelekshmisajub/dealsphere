"""
Django settings for DealSphere
Generated with premium AI configuration
"""

from pathlib import Path
import os
import sys

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


def _load_local_env_file():
    """Load simple KEY=VALUE and PowerShell-style $env:KEY='VALUE' entries from .env."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists() or not env_path.is_file():
        return

    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        key = None
        value = None

        if line.startswith("$env:") and "=" in line:
            key_part, value_part = line[5:].split("=", 1)
            key = key_part.strip()
            value = value_part.strip()
        elif "=" in line:
            key_part, value_part = line.split("=", 1)
            key = key_part.strip()
            value = value_part.strip()

        if not key:
            continue

        if value is None:
            value = ""

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


_load_local_env_file()

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-premium-key-for-dealsphere-shopping-system'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']
CSRF_TRUSTED_ORIGINS = [
    'http://127.0.0.1:8000',
    'http://localhost:8000',
    'http://127.0.0.1',
    'http://localhost',
]
TESTING = 'test' in sys.argv

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party apps
    'rest_framework',
    'corsheaders',
    'drf_spectacular',
    
    # Internal apps
    'apps.core',
    'apps.users',
    'apps.merchants',
    # 'apps.ai_engine',  # Temporarily disabled due to ML dependencies
    'apps.admin_panel',
    'apps.api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'dealsphere.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'dealsphere.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            'timeout': 20,  # Increase timeout to 20 seconds
        },
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Authentication
AUTH_USER_MODEL = 'core.User'

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default auto-field
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'DealSphere API',
    'DESCRIPTION': 'Real-data-backed product comparison, merchant, and AI endpoints for DealSphere.',
    'VERSION': '1.0.0',
    'COMPONENT_SPLIT_REQUEST': True,
    'ENUM_NAME_OVERRIDES': {
        'OrderWorkflowStatusEnum': (
            ('pending', 'Pending'),
            ('confirmed', 'Confirmed'),
            ('processing', 'Processing'),
            ('shipped', 'Shipped'),
            ('delivered', 'Delivered'),
            ('cancelled', 'Cancelled'),
        ),
        'PriceMatchRequestStatusEnum': (
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('expired', 'Expired'),
        ),
    },
}

# Import AI settings from settings_ai.py
from .settings_ai import *

# Correct logging mapping (LOGGING_CONFIG must be a string dot-path, LOGGING should be the dict)
# LOGGING_CONFIG = 'logging.config.dictConfig' # This is the default if not set
LOGGING = LOGGING_CONFIG 
LOGGING_CONFIG = 'logging.config.dictConfig' 

# Override dataset paths to local directory
AI_SETTINGS['DATASET_PATHS'] = {
    'amazon': os.path.join(BASE_DIR, 'dataset', 'amazon.csv'),
    'flipkart': os.path.join(BASE_DIR, 'dataset', '_flipkart_com-ecommerce__.csv'),
    'local_stores': os.path.join(BASE_DIR, 'dataset', 'local_store_offer_dataset.csv'),
}

PAYMENT_SETTINGS = {
    'upi_id': os.getenv('DEALSPHERE_UPI_ID', 'dealsphere@upi').strip(),
    'upi_name': os.getenv('DEALSPHERE_UPI_NAME', 'DealSphere Store').strip(),
    'gateway_url': os.getenv('DEALSPHERE_PAYMENT_GATEWAY_URL', '').strip(),
    'gateway_name': os.getenv('DEALSPHERE_PAYMENT_GATEWAY_NAME', 'Online Gateway').strip(),
}
PAYMENT_SETTINGS['upi_enabled'] = bool(PAYMENT_SETTINGS['upi_id'])
PAYMENT_SETTINGS['gateway_enabled'] = bool(PAYMENT_SETTINGS['gateway_url'])

ENABLE_LIVE_PRODUCT_PAGE_ENRICHMENT = (
    os.getenv('DEALSPHERE_ENABLE_LIVE_PRODUCT_PAGE_ENRICHMENT', '0').strip().lower() in {'1', 'true', 'yes', 'on'}
)
ENABLE_EXTERNAL_TRENDING_FEEDS = (
    os.getenv('DEALSPHERE_ENABLE_EXTERNAL_TRENDING_FEEDS', '0').strip().lower() in {'1', 'true', 'yes', 'on'}
)
CATALOG_BOOTSTRAP_READY_CACHE_SECONDS = int(
    os.getenv('DEALSPHERE_CATALOG_BOOTSTRAP_READY_CACHE_SECONDS', '300') or 300
)

AMAZON_REVIEW_API_SETTINGS = {
    'endpoint': os.getenv(
        'DEALSPHERE_AMAZON_REVIEWS_ENDPOINT',
        'https://real-time-amazon-data.p.rapidapi.com/top-product-reviews',
    ).strip(),
    'host': os.getenv(
        'DEALSPHERE_AMAZON_REVIEWS_HOST',
        'real-time-amazon-data.p.rapidapi.com',
    ).strip(),
    'key': os.getenv('DEALSPHERE_AMAZON_REVIEWS_KEY', '').strip(),
    'default_country': os.getenv('DEALSPHERE_AMAZON_REVIEWS_DEFAULT_COUNTRY', 'IN').strip().upper() or 'IN',
    'timeout_seconds': int(os.getenv('DEALSPHERE_AMAZON_REVIEWS_TIMEOUT', '12') or 12),
}
AMAZON_REVIEW_API_SETTINGS['enabled'] = bool(
    AMAZON_REVIEW_API_SETTINGS['endpoint']
    and AMAZON_REVIEW_API_SETTINGS['host']
    and AMAZON_REVIEW_API_SETTINGS['key']
)

AMAZON_PRODUCT_INFO_API_SETTINGS = {
    'endpoint': os.getenv(
        'DEALSPHERE_AMAZON_PRODUCT_INFO_ENDPOINT',
        'https://amazon-pricing-and-product-info.p.rapidapi.com/',
    ).strip(),
    'host': os.getenv(
        'DEALSPHERE_AMAZON_PRODUCT_INFO_HOST',
        'amazon-pricing-and-product-info.p.rapidapi.com',
    ).strip(),
    'key': os.getenv('DEALSPHERE_AMAZON_PRODUCT_INFO_KEY', '').strip(),
    'default_domain': os.getenv('DEALSPHERE_AMAZON_PRODUCT_INFO_DEFAULT_DOMAIN', 'in').strip().lower() or 'in',
    'timeout_seconds': int(os.getenv('DEALSPHERE_AMAZON_PRODUCT_INFO_TIMEOUT', '12') or 12),
}
AMAZON_PRODUCT_INFO_API_SETTINGS['enabled'] = bool(
    AMAZON_PRODUCT_INFO_API_SETTINGS['endpoint']
    and AMAZON_PRODUCT_INFO_API_SETTINGS['host']
    and AMAZON_PRODUCT_INFO_API_SETTINGS['key']
)

EXTERNAL_FASHION_FEED_SETTINGS = {
    'female_footwear_endpoint': os.getenv(
        'DEALSPHERE_FEMALE_FOOTWEAR_ENDPOINT',
        'https://ecommerceflaskapi.vercel.app/api/v1/femalefootwear',
    ).strip(),
    'timeout_seconds': int(os.getenv('DEALSPHERE_FEMALE_FOOTWEAR_TIMEOUT', '12') or 12),
}

PRODUCT_PRICE_HISTORY_API_SETTINGS = {
    'endpoint': os.getenv(
        'DEALSPHERE_PRODUCT_PRICE_HISTORY_ENDPOINT',
        'https://real-time-product-search.p.rapidapi.com/product-price-history',
    ).strip(),
    'host': os.getenv(
        'DEALSPHERE_PRODUCT_PRICE_HISTORY_HOST',
        'real-time-product-search.p.rapidapi.com',
    ).strip(),
    'key': os.getenv('DEALSPHERE_PRODUCT_PRICE_HISTORY_KEY', '').strip(),
    'default_country': os.getenv('DEALSPHERE_PRODUCT_PRICE_HISTORY_DEFAULT_COUNTRY', 'us').strip().lower() or 'us',
    'default_language': os.getenv('DEALSPHERE_PRODUCT_PRICE_HISTORY_DEFAULT_LANGUAGE', 'en').strip().lower() or 'en',
    'timeout_seconds': int(os.getenv('DEALSPHERE_PRODUCT_PRICE_HISTORY_TIMEOUT', '12') or 12),
}
PRODUCT_PRICE_HISTORY_API_SETTINGS['enabled'] = bool(
    PRODUCT_PRICE_HISTORY_API_SETTINGS['endpoint']
    and PRODUCT_PRICE_HISTORY_API_SETTINGS['host']
    and PRODUCT_PRICE_HISTORY_API_SETTINGS['key']
)

# RapidAPI: Real-time Flipkart / Amazon / Myntra / AJIO / Croma product details
REALTIME_PRODUCT_API_SETTINGS = {
    'endpoint': 'https://realtime-flipkart-amazon-myntra-ajio-croma-product-details.p.rapidapi.com/product',
    'host': 'realtime-flipkart-amazon-myntra-ajio-croma-product-details.p.rapidapi.com',
    'key': os.getenv('DEALSPHERE_REALTIME_PRODUCT_KEY', '').strip(),
    'timeout_seconds': int(os.getenv('DEALSPHERE_REALTIME_PRODUCT_TIMEOUT', '12') or 12),
}
REALTIME_PRODUCT_API_SETTINGS['enabled'] = bool(
    REALTIME_PRODUCT_API_SETTINGS['endpoint']
    and REALTIME_PRODUCT_API_SETTINGS['host']
    and REALTIME_PRODUCT_API_SETTINGS['key']
)
