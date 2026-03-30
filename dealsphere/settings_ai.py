"""
Django Settings for AI Integration
Configuration for AI models, caching, and real datasets
"""

import os
from pathlib import Path

# AI Model Settings
AI_SETTINGS = {
    # Dataset paths
    'DATASET_PATHS': {
        'amazon': 'dataset/amazon.csv',
        'flipkart': 'dataset/_flipkart_com-ecommerce__.csv',
        'local_stores': 'dataset/local_store_offer_dataset.csv',
        'retail_images': 'dataset/retail_product_checkout/'
    },
    
    # Model paths and settings
    'MODEL_PATHS': {
        'ml_ranker': 'apps/ai_engine/models/saved_models/ml_ranker.pkl',
        'price_predictor': 'apps/ai_engine/models/saved_models/price_predictor.pkl',
        'basket_optimizer': 'apps/ai_engine/models/saved_models/basket_optimizer.pkl',
        'barcode_scanner': 'apps/ai_engine/models/saved_models/barcode_scanner.pkl',
        'computer_vision': 'apps/ai_engine/models/saved_models/computer_vision.pkl'
    },
    
    # Cache settings for AI results
    'CACHE_TIMEOUTS': {
        'product_ranking': 300,  # 5 minutes
        'basket_optimization': 600,  # 10 minutes
        'price_prediction': 1800,  # 30 minutes
        'user_recommendations': 900,  # 15 minutes
        'merchant_insights': 3600,  # 1 hour
        'barcode_results': 300,  # 5 minutes
        'image_identification': 600  # 10 minutes
    },
    
    # AI model parameters
    'ML_RANKER': {
        'features': [
            'price', 'original_price', 'discount_percentage', 'rating',
            'rating_count', 'delivery_time', 'merchant_rating',
            'location_match', 'user_preference_match', 'search_relevance'
        ],
        'model_type': 'RandomForestRegressor',
        'n_estimators': 100,
        'random_state': 42
    },
    
    'PRICE_PREDICTOR': {
        'sequence_length': 30,  # 30 days of history
        'prediction_days': 7,  # Predict 7 days ahead
        'model_type': 'LSTM',
        'lstm_units': 50,
        'dropout_rate': 0.2,
        'epochs': 100,
        'batch_size': 32
    },
    
    'BASKET_OPTIMIZER': {
        'max_stores': 5,  # Consider up to 5 stores
        'max_distance_km': 10,  # Max distance between stores
        'delivery_cost_per_km': 5,  # ₹5 per km delivery
        'time_cost_per_hour': 50  # ₹50 per hour time cost
    },
    
    # Real dataset validation
    'DATASET_VALIDATION': {
        'min_products': 1000,  # Minimum products required
        'min_merchants': 50,   # Minimum merchants required
        'min_offers': 500,     # Minimum offers required
        'required_columns': {
            'amazon': ['product_id', 'product_name', 'category', 'discounted_price', 'actual_price', 'rating'],
            'flipkart': ['Uniq Id', 'Product Title', 'Brand', 'Mrp', 'Price'],
            'local_stores': ['store_name', 'product_name', 'offer_price_inr', 'original_price_inr']
        }
    },
    
    # Performance settings
    'PERFORMANCE': {
        'enable_caching': True,
        'async_processing': True,
        'batch_size': 32,
        'max_concurrent_requests': 10
    }
}

# Redis Configuration for AI Caching
REDIS_CONFIG = {
    'host': 'localhost',
    'port': 6379,
    'db': 1,  # Separate DB for AI caching
    'password': None,
    'socket_timeout': 5,
    'connection_pool_kwargs': {
        'max_connections': 20,
        'retry_on_timeout': True
    }
}

# Celery Configuration for AI Tasks
CELERY_CONFIG = {
    'broker_url': 'redis://localhost:6379/0',
    'result_backend': 'redis://localhost:6379/0',
    'task_serializer': 'json',
    'accept_content': ['json'],
    'result_serializer': 'json',
    'timezone': 'Asia/Kolkata',
    'enable_utc': True,
    'task_routes': {
        'apps.ai_engine.tasks.train_models': {'queue': 'ai_training'},
        'apps.ai_engine.tasks.process_image': {'queue': 'image_processing'},
        'apps.ai_engine.tasks.optimize_basket': {'queue': 'basket_optimization'}
    }
}

# Logging Configuration for AI
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'ai_verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'ai_simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'ai_file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'logs/ai_engine.log',
            'formatter': 'ai_verbose',
        },
        'ai_console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'ai_simple',
        },
    },
    'loggers': {
        'apps.ai_engine': {
            'handlers': ['ai_file', 'ai_console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'apps.api.services_ai': {
            'handlers': ['ai_file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# API Rate Limiting for AI Endpoints
AI_RATE_LIMITS = {
    'ranked_products': '100/hour',
    'basket_optimization': '20/hour',
    'price_prediction': '50/hour',
    'barcode_search': '200/hour',
    'image_identification': '30/hour',
    'smart_notifications': '100/hour',
    'personalized_recommendations': '200/hour'
}

# AI Feature Flags
AI_FEATURES = {
    'enable_ml_ranking': True,
    'enable_price_prediction': True,
    'enable_basket_optimization': True,
    'enable_barcode_scanning': True,
    'enable_image_identification': True,
    'enable_smart_notifications': True,
    'enable_demand_forecasting': True,
    'enable_competitor_analysis': True,
    'enable_pricing_suggestions': True,
    'enable_inventory_optimization': True
}

# Model Training Settings
TRAINING_SETTINGS = {
    'auto_retrain': True,
    'retrain_interval_hours': 24,  # Retrain every 24 hours
    'min_new_data_points': 100,  # Minimum new data points before retraining
    'backup_models': True,
    'model_validation_split': 0.2,  # 20% for validation
    'early_stopping_patience': 10
}

# Security Settings for AI
AI_SECURITY = {
    'max_image_size_mb': 10,
    'allowed_image_formats': ['jpg', 'jpeg', 'png', 'webp'],
    'barcode_validation': True,
    'rate_limit_by_user': True,
    'audit_ai_requests': True
}

# Integration Settings
INTEGRATION_SETTINGS = {
    'external_apis': {
        'google_vision': False,  # Set to True to use Google Vision API
        'amazon_rekognition': False,  # Set to True to use Amazon Rekognition
        'azure_cognitive': False  # Set to True to use Azure Cognitive Services
    },
    'webhook_endpoints': {
        'price_drop_alerts': '/api/v1/webhooks/price-drops/',
        'inventory_alerts': '/api/v1/webhooks/inventory/',
        'competitor_alerts': '/api/v1/webhooks/competitors/'
    }
}
