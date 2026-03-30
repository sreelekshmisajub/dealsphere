# DealSphere Production Folder Structure

```
dealsphere/
├── manage.py                                    # Django management script
├── requirements.txt                             # Python dependencies
├── requirements-dev.txt                         # Development dependencies
├── docker-compose.yml                           # Docker orchestration
├── Dockerfile                                   # Container configuration
├── .env.example                                 # Environment variables template
├── .gitignore                                   # Git ignore rules
├── README.md                                    # Project documentation
├── pyproject.toml                               # Project configuration
├── Makefile                                     # Common commands
│
├── dealsphere/                                  # Django project root
│   ├── __init__.py
│   ├── settings/                                # Settings configuration
│   │   ├── __init__.py
│   │   ├── base.py                              # Base settings
│   │   ├── development.py                      # Development environment
│   │   ├── production.py                       # Production environment
│   │   └── testing.py                           # Test environment
│   ├── urls.py                                  # Main URL configuration
│   ├── wsgi.py                                  # WSGI application
│   ├── asgi.py                                  # ASGI application
│   └── celery.py                                # Celery configuration
│
├── apps/                                        # Django applications
│   ├── __init__.py
│   │
│   ├── users/                                   # User management app
│   │   ├── __init__.py
│   │   ├── admin.py                             # Django admin configuration
│   │   ├── apps.py                              # App configuration
│   │   ├── models.py                            # User models (CustomUser, Profile)
│   │   ├── views.py                             # User views (Login, Register, Profile)
│   │   ├── serializers.py                       # DRF serializers
│   │   ├── urls.py                              # User URL patterns
│   │   ├── permissions.py                       # Custom permissions
│   │   ├── managers.py                          # Custom model managers
│   │   ├── signals.py                           # User signals
│   │   ├── forms.py                             # User forms
│   │   ├── migrations/                          # Database migrations
│   │   └── tests/                               # User app tests
│   │       ├── __init__.py
│   │       ├── test_models.py
│   │       ├── test_views.py
│   │       └── test_serializers.py
│   │
│   ├── products/                                # Product catalog app
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py                            # Product models (Product, Category, Brand)
│   │   ├── views.py                             # Product views (List, Detail, Search)
│   │   ├── serializers.py                       # Product serializers
│   │   ├── urls.py                              # Product URL patterns
│   │   ├── filters.py                           # Product filters
│   │   ├── managers.py                          # Product managers
│   │   ├── tasks.py                             # Celery tasks (price updates)
│   │   ├── utils.py                             # Product utilities
│   │   ├── migrations/
│   │   └── tests/
│   │
│   ├── merchants/                               # Merchant management app
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py                            # Merchant models (Store, Inventory, Offer)
│   │   ├── views.py                             # Merchant views (Dashboard, Management)
│   │   ├── serializers.py                       # Merchant serializers
│   │   ├── urls.py                              # Merchant URL patterns
│   │   ├── permissions.py                       # Merchant permissions
│   │   ├── managers.py                          # Merchant managers
│   │   ├── signals.py                           # Merchant signals
│   │   ├── migrations/
│   │   └── tests/
│   │
│   ├── ai_engine/                               # AI/ML engine app
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py                            # AI models (Prediction, Recommendation)
│   │   ├── views.py                             # AI views (Prediction, Analysis)
│   │   ├── serializers.py                       # AI serializers
│   │   ├── urls.py                              # AI URL patterns
│   │   ├── tasks.py                             # AI Celery tasks
│   │   ├── utils.py                             # AI utilities
│   │   ├── migrations/
│   │   └── models/                              # AI model files
│   │       ├── __init__.py
│   │       ├── computer_vision/                 # Computer vision models
│   │       │   ├── __init__.py
│   │       │   ├── product_classifier.py       # Product classification model
│   │       │   ├── object_detector.py           # Object detection (YOLO)
│   │       │   ├── image_recognizer.py          # Image recognition (ResNet)
│   │       │   ├── barcode_scanner.py           # Barcode processing
│   │       │   ├── model_weights/               # Trained model weights
│   │       │   │   ├── resnet50_weights.pth
│   │       │   │   ├── yolo_v8_weights.pt
│   │       │   │   └── siamese_network.pth
│   │       │   └── preprocessing/               # Image preprocessing
│   │       │       ├── __init__.py
│   │       │       ├── image_augmentation.py
│   │       │       └── feature_extraction.py
│   │       ├── price_prediction/                # Price forecasting models
│   │       │   ├── __init__.py
│   │       │   ├── lstm_predictor.py            # LSTM price prediction
│   │       │   ├── arima_model.py               # ARIMA time series
│   │       │   ├── price_analyzer.py            # Price analysis
│   │       │   ├── model_weights/
│   │       │   │   ├── lstm_model.h5
│   │       │   │   └── arima_model.pkl
│   │       │   └── data_processing/             # Data preprocessing
│   │       │       ├── __init__.py
│   │       │       ├── feature_engineering.py
│   │       │       └── data_cleaning.py
│   │       ├── ranking_engine/                  # Product ranking models
│   │       │   ├── __init__.py
│   │       │   ├── ml_ranker.py                 # ML-based ranking
│   │       │   ├── weighted_scorer.py            # Weighted scoring algorithm
│   │       │   ├── basket_optimizer.py           # Shopping basket optimization
│   │       │   ├── price_matcher.py              # Price matching algorithm
│   │       │   └── model_weights/
│   │       │       ├── ranking_model.pkl
│   │       │       └── optimizer_model.pkl
│   │       ├── nlp_processing/                   # Natural language processing
│   │       │   ├── __init__.py
│   │       │   ├── text_classifier.py           # Text classification
│   │       │   ├── sentiment_analyzer.py        # Sentiment analysis
│   │       │   ├── entity_extractor.py          # Named entity recognition
│   │       │   ├── model_weights/
│   │       │   │   ├── bert_model.pth
│   │       │   │   └── sentiment_model.pkl
│   │       │   └── preprocessing/
│   │       │       ├── __init__.py
│   │       │       ├── tokenization.py
│   │       │       └── text_cleaning.py
│   │       └── recommendation/                   # Recommendation system
│   │           ├── __init__.py
│   │           ├── collaborative_filtering.py   # Collaborative filtering
│   │           ├── content_based.py              # Content-based filtering
│   │           ├── hybrid_recommender.py        # Hybrid recommendation
│   │           ├── model_weights/
│   │           │   ├── cf_model.pkl
│   │           │   └── cb_model.pkl
│   │           └── preprocessing/
│   │               ├── __init__.py
│   │               └── user_item_matrix.py
│   │
│   ├── orders/                                  # Order management app
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py                            # Order models (Order, OrderItem)
│   │   ├── views.py                             # Order views (Create, Track, History)
│   │   ├── serializers.py                       # Order serializers
│   │   ├── urls.py                              # Order URL patterns
│   │   ├── permissions.py                       # Order permissions
│   │   ├── managers.py                          # Order managers
│   │   ├── signals.py                           # Order signals
│   │   ├── utils.py                             # Order utilities
│   │   ├── migrations/
│   │   └── tests/
│   │
│   ├── notifications/                           # Notification system app
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── apps.py
│   │   ├── models.py                            # Notification models
│   │   ├── views.py                             # Notification views
│   │   ├── serializers.py                       # Notification serializers
│   │   ├── urls.py                              # Notification URL patterns
│   │   ├── tasks.py                             # Celery notification tasks
│   │   ├── services.py                          # Notification services
│   │   ├── channels/                            # WebSocket channels
│   │   │   ├── __init__.py
│   │   │   ├── consumers.py                     # WebSocket consumers
│   │   │   └── routing.py                       # WebSocket routing
│   │   ├── migrations/
│   │   └── tests/
│   │
│   └── admin_panel/                              # Admin dashboard app
│       ├── __init__.py
│       ├── admin.py
│       ├── apps.py
│       ├── models.py                            # Admin-specific models
│       ├── views.py                             # Admin dashboard views
│       ├── serializers.py                       # Admin serializers
│       ├── urls.py                              # Admin URL patterns
│       ├── permissions.py                       # Admin permissions
│       ├── managers.py                          # Admin managers
│       ├── dashboard.py                         # Dashboard utilities
│       ├── analytics.py                         # Analytics utilities
│       ├── migrations/
│       └── tests/
│
├── services/                                    # Business logic services
│   ├── __init__.py
│   ├── payment_service.py                       # Payment processing service
│   ├── email_service.py                         # Email sending service
│   ├── sms_service.py                           # SMS sending service
│   ├── whatsapp_service.py                      # WhatsApp API service
│   ├── geolocation_service.py                   # GPS and location service
│   ├── search_service.py                        # Search indexing service
│   ├── cache_service.py                         # Cache management service
│   ├── file_service.py                          # File upload/management service
│   ├── notification_service.py                  # Notification management service
│   ├── analytics_service.py                     # Analytics data service
│   ├── integration_service.py                   # External API integration service
│   └── security_service.py                     # Security utilities service
│
├── utils/                                       # Utility functions
│   ├── __init__.py
│   ├── decorators.py                            # Custom decorators
│   ├── validators.py                            # Custom validators
│   ├── helpers.py                               # Helper functions
│   ├── constants.py                             # Application constants
│   ├── exceptions.py                            # Custom exceptions
│   ├── middleware.py                            # Custom middleware
│   ├── permissions.py                           # Permission utilities
│   ├── pagination.py                            # Custom pagination
│   ├── filters.py                               # Custom filters
│   ├── formatters.py                            # Data formatting utilities
│   ├── encryption.py                            # Encryption utilities
│   ├── logging.py                               # Logging configuration
│   ├── testing.py                               # Testing utilities
│   └── performance.py                           # Performance monitoring
│
├── core/                                        # Core application components
│   ├── __init__.py
│   ├── models.py                                # Abstract base models
│   ├── managers.py                              # Base model managers
│   ├── views.py                                 # Base view classes
│   ├── serializers.py                           # Base serializer classes
│   ├── permissions.py                           # Base permission classes
│   ├── mixins.py                                # Generic mixins
│   ├── fields.py                                # Custom model fields
│   └── exceptions.py                            # Core exceptions
│
├── templates/                                   # HTML templates
│   ├── base.html                                # Base template
│   ├── accounts/                                # User templates
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── profile.html
│   │   └── dashboard.html
│   ├── products/                                # Product templates
│   │   ├── list.html
│   │   ├── detail.html
│   │   ├── search.html
│   │   └── compare.html
│   ├── merchants/                               # Merchant templates
│   │   ├── dashboard.html
│   │   ├── inventory.html
│   │   ├── offers.html
│   │   └── analytics.html
│   ├── orders/                                  # Order templates
│   │   ├── create.html
│   │   ├── detail.html
│   │   ├── history.html
│   │   └── tracking.html
│   ├── admin/                                   # Admin templates
│   │   ├── dashboard.html
│   │   ├── users.html
│   │   ├── merchants.html
│   │   └── analytics.html
│   ├── errors/                                  # Error pages
│   │   ├── 404.html
│   │   ├── 500.html
│   │   └── 403.html
│   └── components/                              # Template components
│       ├── navbar.html
│       ├── footer.html
│       ├── sidebar.html
│       └── pagination.html
│
├── static/                                      # Static files
│   ├── css/                                     # CSS files
│   │   ├── main.css
│   │   ├── admin.css
│   │   ├── mobile.css
│   │   └── components/
│   │       ├── navbar.css
│   │       ├── cards.css
│   │       └── forms.css
│   ├── js/                                      # JavaScript files
│   │   ├── main.js
│   │   ├── admin.js
│   │   ├── search.js
│   │   ├── maps.js
│   │   ├── charts.js
│   │   └── components/
│   │       ├── modal.js
│   │       ├── dropdown.js
│   │       └── validation.js
│   ├── images/                                  # Static images
│   │   ├── logo.png
│   │   ├── icons/
│   │   ├── banners/
│   │   └── placeholders/
│   ├── fonts/                                   # Font files
│   │   ├── custom-font.woff2
│   │   └── icons/
│   └── plugins/                                 # Third-party plugins
│       ├── bootstrap/
│       ├── jquery/
│       └── chart.js/
│
├── media/                                       # User uploaded media
│   ├── products/                                # Product images
│   │   ├── thumbnails/
│   │   ├── full_size/
│   │   └── temp/
│   ├── users/                                   # User avatars
│   │   ├── avatars/
│   │   └── banners/
│   ├── stores/                                  # Store images
│   │   ├── logos/
│   │   ├── interiors/
│   │   └── products/
│   └── uploads/                                 # General uploads
│       ├── documents/
│       ├── videos/
│       └── temp/
│
├── dataset/                                     # Dataset files
│   ├── raw/                                     # Raw datasets
│   │   ├── amazon.csv                          # Amazon product data
│   │   ├── flipkart.csv                         # Flipkart product data
│   │   ├── local_stores.csv                     # Local store data
│   │   └── retail_product_checkout/             # Retail checkout dataset
│   │       ├── instances_train2019.json
│   │       ├── instances_val2019.json
│   │       ├── instances_test2019.json
│   │       ├── train2019/
│   │       ├── val2019/
│   │       └── test2019/
│   ├── processed/                               # Processed datasets
│   │   ├── cleaned_products.csv
│   │   ├── normalized_prices.csv
│   │   ├── categorized_products.csv
│   │   └── store_inventory.csv
│   ├── training/                                # Training data for AI models
│   │   ├── computer_vision/
│   │   │   ├── product_images/
│   │   │   ├── annotations/
│   │   │   └── labels/
│   │   ├── price_prediction/
│   │   │   ├── historical_prices.csv
│   │   │   ├── market_events.csv
│   │   │   └── features.csv
│   │   ├── nlp/
│   │   │   ├── product_descriptions.txt
│   │   │   ├── reviews.txt
│   │   │   └── categories.txt
│   │   └── recommendation/
│   │       ├── user_interactions.csv
│   │       ├── product_views.csv
│   │       └── purchase_history.csv
│   ├── validation/                              # Validation datasets
│   │   ├── test_products.csv
│   │   ├── test_prices.csv
│   │   └── test_images/
│   └── metadata/                                # Dataset metadata
│       ├── schema.json
│       ├── data_dictionary.json
│       ├── quality_report.json
│       └── processing_log.json
│
├── logs/                                        # Application logs
│   ├── django.log                               # Django application logs
│   ├── celery.log                               # Celery task logs
│   ├── error.log                                # Error logs
│   ├── access.log                               # Access logs
│   ├── security.log                             # Security logs
│   ├── performance.log                          # Performance logs
│   └── ai/                                      # AI/ML model logs
│       ├── training.log
│       ├── prediction.log
│       └── model_performance.log
│
├── tests/                                       # Test suite
│   ├── __init__.py
│   ├── conftest.py                              # Pytest configuration
│   ├── factories.py                             # Test factories
│   ├── fixtures/                                # Test fixtures
│   │   ├── users.json
│   │   ├── products.json
│   │   └── stores.json
│   ├── integration/                             # Integration tests
│   │   ├── __init__.py
│   │   ├── test_api_integration.py
│   │   ├── test_payment_integration.py
│   │   └── test_external_apis.py
│   ├── unit/                                    # Unit tests
│   │   ├── __init__.py
│   │   ├── test_models.py
│   │   ├── test_views.py
│   │   ├── test_services.py
│   │   └── test_utils.py
│   ├── performance/                             # Performance tests
│   │   ├── __init__.py
│   │   ├── test_load.py
│   │   ├── test_stress.py
│   │   └── test_memory.py
│   └── ai/                                      # AI/ML tests
│       ├── __init__.py
│       ├── test_models.py
│       ├── test_predictions.py
│       └── test_training.py
│
├── scripts/                                     # Utility scripts
│   ├── __init__.py
│   ├── setup_database.py                       # Database setup script
│   ├── migrate_datasets.py                     # Dataset migration script
│   ├── train_models.py                          # AI model training script
│   ├── backup_data.py                           # Data backup script
│   ├── cleanup_media.py                         # Media cleanup script
│   ├── generate_reports.py                     # Report generation script
│   ├── deploy.sh                                # Deployment script
│   └── health_check.py                         # Health check script
│
├── docs/                                        # Documentation
│   ├── README.md                                # Project README
│   ├── API.md                                   # API documentation
│   ├── DEPLOYMENT.md                            # Deployment guide
│   ├── DEVELOPMENT.md                           # Development setup
│   ├── ARCHITECTURE.md                          # Architecture documentation
│   ├── MODELS.md                                # Model documentation
│   ├── AI_MODELS.md                             # AI/ML model documentation
│   ├── DATASETS.md                              # Dataset documentation
│   ├── SECURITY.md                              # Security documentation
│   ├── PERFORMANCE.md                           # Performance documentation
│   ├── CHANGELOG.md                             # Changelog
│   └── images/                                  # Documentation images
│       ├── architecture/
│       ├── diagrams/
│       └── screenshots/
│
├── deployment/                                  # Deployment configuration
│   ├── docker/                                  # Docker configurations
│   │   ├── Dockerfile.prod                      # Production Dockerfile
│   │   ├── Dockerfile.dev                       # Development Dockerfile
│   │   ├── docker-compose.prod.yml             # Production compose
│   │   └── docker-compose.dev.yml              # Development compose
│   ├── kubernetes/                              # Kubernetes configurations
│   │   ├── namespace.yaml
│   │   ├── configmap.yaml
│   │   ├── secret.yaml
│   │   ├── deployment.yaml
│   │   ├── service.yaml
│   │   ├── ingress.yaml
│   │   └── hpa.yaml
│   ├── nginx/                                   # Nginx configuration
│   │   ├── nginx.conf
│   │   ├── ssl/
│   │   └── sites-available/
│   ├── systemd/                                 # Systemd service files
│   │   ├── dealsphere.service
│   │   ├── dealsphere-celery.service
│   │   └── dealsphere-celerybeat.service
│   └── monitoring/                              # Monitoring configuration
│       ├── prometheus.yml
│       ├── grafana/
│       └── alertmanager.yml
│
└── monitoring/                                  # Monitoring and metrics
    ├── prometheus/                              # Prometheus metrics
    │   ├── rules/
    │   └── targets/
    ├── grafana/                                 # Grafana dashboards
    │   ├── dashboards/
    │   └── provisioning/
    ├── logs/                                    # Log aggregation
    │   ├── filebeat.yml
    │   └── logstash.conf
    └── alerts/                                  # Alert configurations
        ├── rules.yml
        └── templates/
```

## Folder Explanations

### Root Level
- **manage.py**: Django's command-line utility for administrative tasks
- **requirements.txt**: Python package dependencies for production
- **requirements-dev.txt**: Additional dependencies for development
- **docker-compose.yml**: Multi-container Docker orchestration
- **Dockerfile**: Container image build configuration
- **.env.example**: Template for environment variables
- **.gitignore**: Git version control ignore rules
- **README.md**: Project overview and setup instructions
- **pyproject.toml**: Modern Python project configuration
- **Makefile**: Common development and deployment commands

### Django Project (dealsphere/)
- **settings/**: Environment-specific configuration files
- **urls.py**: Main URL routing configuration
- **wsgi.py**: WSGI interface for production servers
- **asgi.py**: ASGI interface for async support
- **celery.py**: Celery distributed task queue configuration

### Django Apps (apps/)
- **users/**: User authentication, profiles, and management
- **products/**: Product catalog, categories, and inventory
- **merchants/**: Store management, merchant tools, and analytics
- **ai_engine/**: AI/ML models, predictions, and intelligent services
- **orders/**: Order processing, tracking, and management
- **notifications/**: Real-time alerts, emails, and messaging
- **admin_panel/**: Administrative dashboard and system management

### AI Engine Models (ai_engine/models/)
- **computer_vision/**: Product recognition, barcode scanning, image processing
- **price_prediction/**: LSTM forecasting, ARIMA models, trend analysis
- **ranking_engine/**: ML-based product ranking and optimization
- **nlp_processing/**: Text analysis, sentiment, entity extraction
- **recommendation/**: Collaborative filtering, content-based recommendations

### Services Layer (services/)
- **payment_service.py**: Payment gateway integration and processing
- **email_service.py**: Email sending and template management
- **sms_service.py**: SMS notifications and OTP services
- **whatsapp_service.py**: WhatsApp Business API integration
- **geolocation_service.py**: GPS, mapping, and location services
- **search_service.py**: Elasticsearch indexing and search functionality
- **cache_service.py**: Redis cache management and optimization
- **file_service.py**: File upload, storage, and media management
- **notification_service.py**: Multi-channel notification management
- **analytics_service.py**: Data analytics and reporting services
- **integration_service.py**: External API integrations (Amazon, Flipkart)
- **security_service.py**: Security utilities and encryption services

### Utils Layer (utils/)
- **decorators.py**: Custom function and method decorators
- **validators.py**: Data validation and sanitization functions
- **helpers.py**: General utility helper functions
- **constants.py**: Application-wide constants and enums
- **exceptions.py**: Custom exception classes
- **middleware.py**: Django middleware components
- **permissions.py**: Permission checking and role management
- **pagination.py**: Custom pagination classes
- **filters.py**: Data filtering and query utilities
- **formatters.py**: Data formatting and transformation
- **encryption.py**: Encryption and decryption utilities
- **logging.py**: Logging configuration and utilities
- **testing.py**: Testing utilities and helpers
- **performance.py**: Performance monitoring and optimization

### Core Components (core/)
- **models.py**: Abstract base models and common model functionality
- **managers.py**: Base model managers and querysets
- **views.py**: Base view classes and common view functionality
- **serializers.py**: Base serializer classes and common serialization
- **permissions.py**: Base permission classes and authorization
- **mixins.py**: Generic mixins for models, views, and serializers
- **fields.py**: Custom model field types
- **exceptions.py**: Core exception classes

### Templates (templates/)
- **base.html**: Master template with common layout
- **accounts/**: User authentication and profile templates
- **products/**: Product display, search, and comparison templates
- **merchants/**: Merchant dashboard and management templates
- **orders/**: Order creation, tracking, and history templates
- **admin/**: Administrative interface templates
- **errors/**: Custom error page templates
- **components/**: Reusable template components

### Static Files (static/)
- **css/**: Stylesheets organized by component and page
- **js/**: JavaScript files for frontend functionality
- **images/**: Static images, icons, and graphics
- **fonts/**: Custom fonts and icon fonts
- **plugins/**: Third-party libraries and plugins

### Media Files (media/)
- **products/**: User-uploaded product images and media
- **users/**: User avatars and profile images
- **stores/**: Store logos, photos, and promotional media
- **uploads/**: General file uploads and temporary files

### Dataset (dataset/)
- **raw/**: Original, unprocessed datasets from external sources
- **processed/**: Cleaned and preprocessed data for application use
- **training/**: Training datasets for AI/ML models
- **validation/**: Validation and test datasets
- **metadata/**: Dataset documentation and quality reports

### Logs (logs/)
- **django.log**: Django application logs and debug information
- **celery.log**: Celery task execution and background job logs
- **error.log**: Application error logs and stack traces
- **access.log**: HTTP request and access logs
- **security.log**: Security events and authentication logs
- **performance.log**: Performance metrics and monitoring data
- **ai/**: AI/ML model training and prediction logs

### Tests (tests/)
- **integration/**: End-to-end integration tests
- **unit/**: Unit tests for individual components
- **performance/**: Load testing and performance benchmarks
- **ai/**: AI/ML model testing and validation

### Scripts (scripts/)
- **setup_database.py**: Database initialization and setup
- **migrate_datasets.py**: Dataset migration and import utilities
- **train_models.py**: AI model training and evaluation scripts
- **backup_data.py**: Automated data backup procedures
- **cleanup_media.py**: Media file cleanup and optimization
- **generate_reports.py**: Automated report generation
- **deploy.sh**: Application deployment automation
- **health_check.py**: System health monitoring and checks

### Documentation (docs/)
- **API.md**: REST API documentation and examples
- **DEPLOYMENT.md**: Production deployment guide
- **DEVELOPMENT.md**: Development environment setup
- **ARCHITECTURE.md**: System architecture documentation
- **MODELS.md**: Data models and relationships
- **AI_MODELS.md**: AI/ML model documentation
- **DATASETS.md**: Dataset descriptions and usage
- **SECURITY.md**: Security policies and procedures
- **PERFORMANCE.md**: Performance optimization guide

### Deployment (deployment/)
- **docker/**: Container configurations for different environments
- **kubernetes/**: K8s deployment manifests and configurations
- **nginx/**: Web server configuration and SSL setup
- **systemd/**: System service configurations
- **monitoring/**: Infrastructure monitoring setup

### Monitoring (monitoring/)
- **prometheus/**: Metrics collection and alerting rules
- **grafana/**: Visualization dashboards and panels
- **logs/**: Log aggregation and processing configuration
- **alerts/**: Alert rules and notification templates
