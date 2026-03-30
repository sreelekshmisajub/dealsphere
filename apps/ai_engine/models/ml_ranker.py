"""
ML Ranking Model for DealSphere
Ranks products based on price, distance, delivery_time, and reliability
"""

import numpy as np
import pandas as pd
import pickle
import os
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score
import logging

logger = logging.getLogger(__name__)

class MLRanker:
    """
    Machine Learning based product ranking system
    Uses weighted scoring with ML optimization
    """
    
    def __init__(self, model_path=None):
        self.model = None
        self.scaler = None
        self.feature_weights = {
            'price': 0.40,      # 40% weight
            'distance': 0.25,   # 25% weight  
            'delivery_time': 0.20, # 20% weight
            'reliability': 0.15  # 15% weight
        }
        self.model_path = model_path or 'ai_engine/models/ranking_engine/model_weights/ranking_model.pkl'
        self.scaler_path = self.model_path.replace('.pkl', '_scaler.pkl').replace('ranking_model', 'scaler')
        
    def load_data(self):
        """Load and prepare training data from real datasets"""
        try:
            # Load Amazon dataset
            amazon_path = 'dataset/amazon.csv'
            amazon_df = pd.read_csv(amazon_path)
            
            # Load local stores dataset
            local_path = 'dataset/local_store_offer_dataset.csv'
            local_df = pd.read_csv(local_path)
            
            # Prepare training data
            training_data = []
            
            # Process Amazon data
            for _, row in amazon_df.iterrows():
                # Simulate distance and delivery time for online stores
                distance = np.random.uniform(5, 50)  # 5-50 km from warehouse
                delivery_time = np.random.uniform(1, 7)  # 1-7 days
                
                # Calculate reliability based on rating
                rating = float(row.get('rating', 3.5))
                reliability = min(rating / 5.0, 1.0)  # Normalize to 0-1
                
                # Extract price
                price_str = row.get('discounted_price', '₹0').replace('₹', '').replace(',', '')
                try:
                    price = float(price_str)
                except:
                    price = 0
                
                # Calculate score based on features
                score = self._calculate_manual_score(price, distance, delivery_time, reliability)
                
                training_data.append({
                    'price': price,
                    'distance': distance,
                    'delivery_time': delivery_time,
                    'reliability': reliability,
                    'score': score,
                    'source': 'amazon'
                })
            
            # Process local store data
            for _, row in local_df.iterrows():
                # Simulate shorter distances for local stores
                distance = np.random.uniform(0.5, 10)  # 0.5-10 km
                delivery_time = np.random.uniform(0.1, 2)  # 0.1-2 hours (same-day delivery)
                
                # Higher reliability for verified local stores
                reliability = np.random.uniform(0.7, 1.0)
                
                price = float(row.get('offer_price_inr', 0))
                
                score = self._calculate_manual_score(price, distance, delivery_time, reliability)
                
                training_data.append({
                    'price': price,
                    'distance': distance,
                    'delivery_time': delivery_time,
                    'reliability': reliability,
                    'score': score,
                    'source': 'local'
                })
            
            df = pd.DataFrame(training_data)
            logger.info(f"Loaded {len(df)} training samples")
            return df
            
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            return None
    
    def _calculate_manual_score(self, price, distance, delivery_time, reliability):
        """Calculate manual score for training data"""
        # Normalize features (lower is better for price, distance, delivery_time)
        price_score = 1.0 / (1.0 + price / 1000)  # Normalize price
        distance_score = 1.0 / (1.0 + distance / 10)  # Normalize distance
        delivery_score = 1.0 / (1.0 + delivery_time)  # Normalize delivery time
        reliability_score = reliability  # Already normalized
        
        # Apply weights
        score = (
            price_score * self.feature_weights['price'] +
            distance_score * self.feature_weights['distance'] +
            delivery_score * self.feature_weights['delivery_time'] +
            reliability_score * self.feature_weights['reliability']
        )
        
        return score * 100  # Scale to 0-100
    
    def train(self):
        """Train the ML ranking model"""
        logger.info("Starting ML Ranker training...")
        
        # Load data
        df = self.load_data()
        if df is None:
            logger.error("Failed to load training data")
            return False
        
        # Prepare features and target
        features = ['price', 'distance', 'delivery_time', 'reliability']
        X = df[features].values
        y = df['score'].values
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        # Scale features
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train model
        self.model = RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            n_jobs=-1
        )
        
        self.model.fit(X_train_scaled, y_train)
        
        # Evaluate
        y_pred = self.model.predict(X_test_scaled)
        mse = mean_squared_error(y_test, y_pred)
        r2 = r2_score(y_test, y_pred)
        
        logger.info(f"Training completed - MSE: {mse:.4f}, R2: {r2:.4f}")
        
        # Save model
        self.save_model()
        
        return True
    
    def predict_score(self, price, distance, delivery_time, reliability):
        """Predict ranking score for a product"""
        if self.model is None:
            self.load_model()
        
        if self.model is None:
            # Fallback to manual calculation
            return self._calculate_manual_score(price, distance, delivery_time, reliability)
        
        # Prepare features
        features = np.array([[price, distance, delivery_time, reliability]])
        
        # Scale features
        if self.scaler:
            features_scaled = self.scaler.transform(features)
        else:
            features_scaled = features
        
        # Predict
        score = self.model.predict(features_scaled)[0]
        
        # Ensure score is in valid range
        score = max(0, min(100, score))
        
        return score
    
    def rank_products(self, products):
        """Rank a list of products"""
        ranked_products = []
        
        for product in products:
            # Extract features
            price = product.get('price', 0)
            distance = product.get('distance', 10)
            delivery_time = product.get('delivery_time', 3)
            reliability = product.get('reliability', 0.8)
            
            # Calculate score
            score = self.predict_score(price, distance, delivery_time, reliability)
            
            # Add score to product
            product['ml_score'] = score
            ranked_products.append(product)
        
        # Sort by score (descending)
        ranked_products.sort(key=lambda x: x['ml_score'], reverse=True)
        
        return ranked_products
    
    def save_model(self):
        """Save trained model and scaler"""
        try:
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            
            with open(self.model_path, 'wb') as f:
                pickle.dump(self.model, f)
            
            with open(self.scaler_path, 'wb') as f:
                pickle.dump(self.scaler, f)
            
            logger.info(f"Model saved to {self.model_path}")
            
        except Exception as e:
            logger.error(f"Error saving model: {e}")
    
    def load_model(self):
        """Load trained model and scaler"""
        try:
            if os.path.exists(self.model_path):
                with open(self.model_path, 'rb') as f:
                    self.model = pickle.load(f)
                
                if os.path.exists(self.scaler_path):
                    with open(self.scaler_path, 'rb') as f:
                        self.scaler = pickle.load(f)
                
                logger.info(f"Model loaded from {self.model_path}")
                return True
            else:
                logger.warning("Model file not found, training new model")
                return self.train()
                
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return False
    
    def update_weights(self, new_weights):
        """Update feature weights"""
        self.feature_weights.update(new_weights)
        logger.info(f"Updated weights: {self.feature_weights}")
    
    def get_feature_importance(self):
        """Get feature importance from trained model"""
        if self.model is None:
            return None
        
        features = ['price', 'distance', 'delivery_time', 'reliability']
        importance = self.model.feature_importances_
        
        return dict(zip(features, importance))


# Example usage
if __name__ == "__main__":
    # Initialize and train the model
    ranker = MLRanker()
    
    # Train the model
    if ranker.train():
        print("Model trained successfully!")
        
        # Test ranking
        test_products = [
            {'price': 500, 'distance': 5, 'delivery_time': 2, 'reliability': 0.9, 'name': 'Product A'},
            {'price': 300, 'distance': 15, 'delivery_time': 5, 'reliability': 0.7, 'name': 'Product B'},
            {'price': 800, 'distance': 2, 'delivery_time': 1, 'reliability': 0.95, 'name': 'Product C'},
        ]
        
        ranked = ranker.rank_products(test_products)
        
        print("\nRanked Products:")
        for i, product in enumerate(ranked, 1):
            print(f"{i}. {product['name']} - Score: {product['ml_score']:.2f}")
        
        # Show feature importance
        importance = ranker.get_feature_importance()
        if importance:
            print(f"\nFeature Importance: {importance}")
    else:
        print("Model training failed!")
