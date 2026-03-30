"""
Training script for all AI/ML models in DealSphere
"""

import os
import sys
import django
import logging

# Setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dealsphere.settings.development')
django.setup()

from apps.ai_engine.models.ml_ranker import MLRanker
from apps.ai_engine.models.computer_vision import ComputerVision
from apps.ai_engine.models.barcode_scanner import BarcodeScanner
from apps.ai_engine.models.basket_optimizer import BasketOptimizer
from apps.ai_engine.models.price_predictor import PricePredictor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def train_all_models():
    """Train all AI/ML models"""
    logger.info("Starting training of all AI/ML models...")
    
    results = {}
    
    # 1. Train ML Ranker
    logger.info("Training ML Ranker...")
    try:
        ranker = MLRanker()
        ranker_success = ranker.train()
        results['ml_ranker'] = ranker_success
        logger.info(f"ML Ranker training: {'SUCCESS' if ranker_success else 'FAILED'}")
    except Exception as e:
        logger.error(f"ML Ranker training failed: {e}")
        results['ml_ranker'] = False
    
    # 2. Train Computer Vision
    logger.info("Training Computer Vision...")
    try:
        cv_system = ComputerVision()
        cv_success = cv_system.train(epochs=10)
        results['computer_vision'] = cv_success
        logger.info(f"Computer Vision training: {'SUCCESS' if cv_success else 'FAILED'}")
    except Exception as e:
        logger.error(f"Computer Vision training failed: {e}")
        results['computer_vision'] = False
    
    # 3. Initialize Barcode Scanner (no training needed, just data loading)
    logger.info("Initializing Barcode Scanner...")
    try:
        scanner = BarcodeScanner()
        scanner_success = scanner.load_database()
        results['barcode_scanner'] = scanner_success
        logger.info(f"Barcode Scanner initialization: {'SUCCESS' if scanner_success else 'FAILED'}")
    except Exception as e:
        logger.error(f"Barcode Scanner initialization failed: {e}")
        results['barcode_scanner'] = False
    
    # 4. Initialize Basket Optimizer (no training needed)
    logger.info("Initializing Basket Optimizer...")
    try:
        optimizer = BasketOptimizer()
        optimizer_success = optimizer.load_model()
        results['basket_optimizer'] = optimizer_success
        logger.info(f"Basket Optimizer initialization: {'SUCCESS' if optimizer_success else 'FAILED'}")
    except Exception as e:
        logger.error(f"Basket Optimizer initialization failed: {e}")
        results['basket_optimizer'] = False
    
    # 5. Train Price Predictor
    logger.info("Training Price Predictor...")
    try:
        predictor = PricePredictor()
        predictor_success = predictor.train(epochs=20)
        results['price_predictor'] = predictor_success
        logger.info(f"Price Predictor training: {'SUCCESS' if predictor_success else 'FAILED'}")
    except Exception as e:
        logger.error(f"Price Predictor training failed: {e}")
        results['price_predictor'] = False
    
    # Summary
    logger.info("\n" + "="*50)
    logger.info("TRAINING SUMMARY")
    logger.info("="*50)
    
    success_count = sum(1 for success in results.values() if success)
    total_count = len(results)
    
    for model, success in results.items():
        status = "✓ SUCCESS" if success else "✗ FAILED"
        logger.info(f"{model.replace('_', ' ').title()}: {status}")
    
    logger.info(f"\nOverall: {success_count}/{total_count} models trained successfully")
    
    if success_count == total_count:
        logger.info("🎉 All models trained successfully!")
        return True
    else:
        logger.warning("⚠️  Some models failed to train. Check logs for details.")
        return False

def test_models():
    """Test all trained models"""
    logger.info("Testing trained models...")
    
    # Test ML Ranker
    try:
        ranker = MLRanker()
        ranker.load_model()
        
        test_products = [
            {'price': 500, 'distance': 5, 'delivery_time': 2, 'reliability': 0.9, 'name': 'Test Product 1'},
            {'price': 300, 'distance': 15, 'delivery_time': 5, 'reliability': 0.7, 'name': 'Test Product 2'},
        ]
        
        ranked = ranker.rank_products(test_products)
        logger.info(f"ML Ranker test: Ranked {len(ranked)} products successfully")
    except Exception as e:
        logger.error(f"ML Ranker test failed: {e}")
    
    # Test Barcode Scanner
    try:
        scanner = BarcodeScanner()
        scanner.load_database()
        
        stats = scanner.get_statistics()
        logger.info(f"Barcode Scanner test: Database contains {stats['total_products']} products")
    except Exception as e:
        logger.error(f"Barcode Scanner test failed: {e}")
    
    # Test Basket Optimizer
    try:
        optimizer = BasketOptimizer()
        
        shopping_list = ["USB Cable", "Smartphone"]
        quantities = [1, 1]
        
        result = optimizer.optimize_basket(shopping_list, quantities)
        logger.info(f"Basket Optimizer test: Optimization completed with {len(result.get('all_options', []))} options")
    except Exception as e:
        logger.error(f"Basket Optimizer test failed: {e}")
    
    # Test Price Predictor
    try:
        predictor = PricePredictor()
        predictor.load_model()
        
        if predictor.price_data:
            sample_product = list(predictor.price_data.keys())[0]
            prediction = predictor.predict_prices(sample_product, 3)
            
            if prediction:
                logger.info(f"Price Predictor test: Successfully predicted prices for {prediction['product_name']}")
            else:
                logger.warning("Price Predictor test: No predictions generated")
        else:
            logger.warning("Price Predictor test: No price data available")
    except Exception as e:
        logger.error(f"Price Predictor test failed: {e}")

if __name__ == "__main__":
    print("DealSphere AI/ML Model Training")
    print("="*50)
    
    # Train all models
    success = train_all_models()
    
    # Test models
    if success:
        print("\nTesting trained models...")
        test_models()
    
    print("\nTraining completed!")
