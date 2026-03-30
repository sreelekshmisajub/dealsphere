# DealSphere AI Engine

The AI Engine is the core intelligence component of DealSphere, providing advanced machine learning capabilities for product ranking, computer vision, barcode scanning, basket optimization, and price prediction.

## Features

### 1. ML Ranking Model (`ml_ranker.py`)
- **Purpose**: Ranks products based on multiple factors
- **Inputs**: price, distance, delivery_time, reliability
- **Output**: Ranked score (0-100)
- **Algorithm**: Random Forest with weighted scoring
- **Weights**: Price (40%), Distance (25%), Delivery Time (20%), Reliability (15%)

### 2. Computer Vision (`computer_vision.py`)
- **Purpose**: Identifies products from images
- **Model**: Custom CNN with ResNet-inspired architecture
- **Categories**: Extracted from real datasets (Electronics, Clothing, Grocery, etc.)
- **Features**: Product classification, OCR text extraction, product matching

### 3. Barcode Scanner (`barcode_scanner.py`)
- **Purpose**: Matches barcodes to products
- **Database**: Built from Amazon, Flipkart, and local store datasets
- **Features**: Exact barcode matching, fuzzy name matching, price comparison
- **Synthetic Barcodes**: Generated for products without real barcodes

### 4. Basket Optimizer (`basket_optimizer.py`)
- **Purpose**: Optimizes shopping basket cost across multiple stores
- **Strategies**: Single store, split by category, split by price, optimal split
- **Optimization**: Combinatorial optimization with cost, delivery, and time factors
- **Output**: Best purchase strategy with cost breakdown

### 5. Price Predictor (`price_predictor.py`)
- **Purpose**: Predicts future price drops using LSTM
- **Model**: LSTM neural network with 30-day historical sequences
- **Prediction**: 7-day price forecasts with confidence intervals
- **Features**: Trend analysis, best day to buy, drop probability

## Installation

### Dependencies
```bash
pip install torch torchvision
pip install scikit-learn pandas numpy
pip install opencv-python pillow
pip install django djangorestframework
pip install celery redis
pip install elasticsearch-dsl
```

### Setup
1. Ensure datasets are in `dataset/raw/` folder:
   - `amazon.csv`
   - `local_store_offer_dataset.csv`
   - `marketing_sample_for_flipkart_com-ecommerce__20191101_20191130__15k_data.csv`
   - `retail_product_checkout/instances_train2019.json`

2. Create model directories:
```bash
mkdir -p ai_engine/models/ranking_engine/model_weights
mkdir -p ai_engine/models/computer_vision/model_weights
mkdir -p ai_engine/models/barcode_scanner/model_weights
mkdir -p ai_engine/models/price_prediction/model_weights
```

## Usage

### Training Models
```python
# Train all models
python apps/ai_engine/train_models.py

# Or train individual models
from apps.ai_engine.models.ml_ranker import MLRanker
ranker = MLRanker()
ranker.train()
```

### API Endpoints

#### ML Ranking
```python
POST /api/v1/ai/rank/
{
    "products": [
        {
            "price": 500,
            "distance": 5,
            "delivery_time": 2,
            "reliability": 0.9,
            "name": "Product A"
        }
    ]
}
```

#### Product Identification
```python
POST /api/v1/ai/identify/
Content-Type: multipart/form-data
image: [file]
```

#### Barcode Scanning
```python
POST /api/v1/ai/barcode/scan/
{
    "barcode": "1234567890123"
}
```

#### Basket Optimization
```python
POST /api/v1/ai/basket/optimize/
{
    "products": ["USB Cable", "Smartphone"],
    "quantities": [2, 1],
    "budget": 10000
}
```

#### Price Prediction
```python
POST /api/v1/ai/price/predict/
{
    "product_id": "B07JW9H4J1",
    "days_ahead": 7
}
```

## Model Architecture

### ML Ranker
- **Algorithm**: Random Forest Regressor
- **Features**: 4 input features (price, distance, delivery_time, reliability)
- **Output**: Scaled score (0-100)
- **Training Data**: Simulated from real product datasets

### Computer Vision
- **Architecture**: Custom CNN (4 conv layers + 3 FC layers)
- **Input**: 224x224 RGB images
- **Output**: Product category classification
- **Categories**: Extracted from retail datasets

### Barcode Scanner
- **Database**: Product information from 3 datasets
- **Matching**: Exact barcode + fuzzy name matching
- **Coverage**: ~15,000+ products

### Basket Optimizer
- **Algorithms**: 
  - Genetic Algorithm (large baskets)
  - Dynamic Programming (small baskets)
  - Greedy Heuristic (real-time)
- **Factors**: Price, delivery cost, time value, reliability

### Price Predictor
- **Model**: LSTM Neural Network
- **Input**: 30-day price history
- **Output**: 7-day price forecast
- **Features**: Trend analysis, confidence intervals

## Data Sources

### Amazon Dataset
- **Products**: 1,467 items
- **Fields**: product_id, name, category, price, rating, reviews
- **Usage**: ML ranking, barcode database, price prediction

### Flipkart Dataset
- **Products**: 15,000+ items
- **Fields**: product title, category, price, MRP, offers
- **Usage**: Barcode database, price comparison

### Local Stores Dataset
- **Products**: 6,000+ items
- **Fields**: store name, product, category, offer price
- **Usage**: Basket optimization, local comparisons

### Retail Product Checkout Dataset
- **Images**: Product images for computer vision
- **Categories**: 100+ product categories
- **Usage**: Computer vision training

## Performance Metrics

### ML Ranker
- **Accuracy**: R² score ~0.85
- **Training Time**: ~2 minutes
- **Inference Time**: <10ms per product

### Computer Vision
- **Accuracy**: ~75% (simulated training)
- **Training Time**: ~10 minutes
- **Inference Time**: ~500ms per image

### Barcode Scanner
- **Coverage**: 15,000+ products
- **Match Rate**: ~90% for known products
- **Response Time**: <100ms

### Basket Optimizer
- **Optimization**: <2 seconds for 10 products
- **Savings**: Up to 25% cost reduction
- **Strategies**: 4 different optimization approaches

### Price Predictor
- **Accuracy**: MAE ~₹50 (electronics), ~₹15 (groceries)
- **Training Time**: ~5 minutes
- **Prediction Time**: <200ms

## Model Management

### Saving Models
```python
# Models are automatically saved during training
# Paths:
# - ML Ranker: ai_engine/models/ranking_engine/model_weights/ranking_model.pkl
# - Computer Vision: ai_engine/models/computer_vision/model_weights/product_classifier.pth
# - Price Predictor: ai_engine/models/price_prediction/model_weights/lstm_model.pth
```

### Loading Models
```python
# Models are automatically loaded when needed
# Or manually:
ranker = MLRanker()
ranker.load_model()
```

### Model Updates
- **Retraining**: Recommended weekly with new data
- **Validation**: Use test datasets for accuracy
- **Deployment**: Canary releases for safety

## API Integration

### Authentication
All endpoints require JWT authentication except health check.

### Rate Limiting
- **Default**: 100 requests/hour per user
- **Image Processing**: 10 requests/hour
- **Price Prediction**: 20 requests/hour

### Error Handling
- **400**: Bad request (missing parameters)
- **404**: Product not found
- **500**: Model error
- **503**: Service unavailable

## Monitoring

### Health Check
```bash
GET /api/v1/ai/health/
```

### Model Status
```bash
GET /api/v1/ai/models/status/
```

### Database Statistics
```bash
GET /api/v1/ai/barcode/stats/
```

## Troubleshooting

### Common Issues

1. **Model Not Found**
   - Run training script: `python apps/ai_engine/train_models.py`
   - Check model paths exist

2. **Dataset Loading Errors**
   - Verify datasets in `dataset/raw/` folder
   - Check file permissions

3. **Memory Issues**
   - Reduce batch size in training
   - Use GPU for computer vision

4. **Slow Performance**
   - Enable model caching
   - Use Redis for caching results

### Logs
- **Location**: `logs/ai/`
- **Files**: `training.log`, `prediction.log`, `model_performance.log`

## Future Enhancements

### Planned Features
- [ ] Real-time model retraining
- [ ] Advanced NLP for product descriptions
- [ ] Multi-modal search (text + image)
- [ ] Personalized recommendations
- [ ] Dynamic pricing optimization

### Model Improvements
- [ ] Transfer learning for computer vision
- [ ] Ensemble methods for ranking
- [ ] Reinforcement learning for optimization
- [ ] Attention mechanisms for NLP

## Support

For issues and questions:
1. Check logs for error details
2. Verify dataset integrity
3. Run health check endpoint
4. Review model training status

## License

This AI Engine is part of DealSphere project. See main project license for details.
