"""
Price Prediction Model for DealSphere
Predicts future price drops using LSTM neural networks
"""

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
import pickle
import os
import logging
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

class PriceDataset(Dataset):
    """Custom dataset for price prediction"""
    
    def __init__(self, sequences, targets):
        self.sequences = torch.FloatTensor(sequences)
        self.targets = torch.FloatTensor(targets)
    
    def __len__(self):
        return len(self.sequences)
    
    def __getitem__(self, idx):
        return self.sequences[idx], self.targets[idx]

class LSTMPricePredictor(nn.Module):
    """LSTM model for price prediction"""
    
    def __init__(self, input_size=1, hidden_size=50, num_layers=2, output_size=1):
        super(LSTMPricePredictor, self).__init__()
        
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        
        # LSTM layers
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, dropout=0.2)
        
        # Fully connected layers
        self.fc1 = nn.Linear(hidden_size, 32)
        self.fc2 = nn.Linear(32, 16)
        self.fc3 = nn.Linear(16, output_size)
        
        # Dropout
        self.dropout = nn.Dropout(0.2)
        
        # Activation
        self.relu = nn.ReLU()
    
    def forward(self, x):
        # Initialize hidden and cell states
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_size).to(x.device)
        
        # LSTM forward pass
        out, _ = self.lstm(x, (h0, c0))
        
        # Take the last output
        out = out[:, -1, :]
        
        # Fully connected layers
        out = self.dropout(out)
        out = self.relu(self.fc1(out))
        out = self.dropout(out)
        out = self.relu(self.fc2(out))
        out = self.fc3(out)
        
        return out

class PricePredictor:
    """
    Price prediction system using LSTM neural networks
    """
    
    def __init__(self, model_path=None):
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model = None
        self.scaler = None
        self.price_data = {}
        
        self.model_path = model_path or 'ai_engine/models/price_prediction/model_weights/lstm_model.pth'
        self.scaler_path = model_path.replace('.pth', '_scaler.pkl').replace('lstm_model', 'scaler')
        self.data_path = model_path.replace('.pth', '_data.pkl').replace('lstm_model', 'data')
        
        # Model parameters
        self.sequence_length = 30  # Use 30 days of historical data
        self.prediction_days = 7   # Predict 7 days ahead
        
        # Load data
        self.load_price_data()
    
    def load_price_data(self):
        """Load and prepare price data from real datasets"""
        try:
            # Load Amazon dataset
            amazon_path = 'dataset/raw/amazon.csv'
            amazon_df = pd.read_csv(amazon_path)
            
            # Load local stores dataset
            local_path = 'dataset/raw/local_store_offer_dataset.csv'
            local_df = pd.read_csv(local_path)
            
            # Load Flipkart dataset
            flipkart_path = 'dataset/raw/marketing_sample_for_flipkart_com-ecommerce__20191101_20191130__15k_data.csv'
            flipkart_df = pd.read_csv(flipkart_path)
            
            # Process Amazon data
            self._process_amazon_prices(amazon_df)
            
            # Process local store data
            self._process_local_prices(local_df)
            
            # Process Flipkart data
            self._process_flipkart_prices(flipkart_df)
            
            logger.info(f"Loaded price data for {len(self.price_data)} products")
            
        except Exception as e:
            logger.error(f"Error loading price data: {e}")
    
    def _process_amazon_prices(self, df):
        """Process Amazon price data"""
        for _, row in df.iterrows():
            product_id = row.get('product_id', '')
            product_name = row.get('product_name', '')
            
            # Extract price
            price_str = row.get('discounted_price', '₹0').replace('₹', '').replace(',', '')
            try:
                current_price = float(price_str)
            except:
                continue
            
            # Generate historical price data
            historical_prices = self._generate_historical_prices(current_price, product_name)
            
            self.price_data[product_id] = {
                'name': product_name,
                'source': 'Amazon',
                'current_price': current_price,
                'historical_prices': historical_prices,
                'last_updated': datetime.now()
            }
    
    def _process_local_prices(self, df):
        """Process local store price data"""
        for _, row in df.iterrows():
            product_name = row.get('product_name', '')
            store_name = row.get('store_name', '')
            key = f"{store_name}_{product_name}"
            
            current_price = float(row.get('offer_price_inr', 0))
            original_price = float(row.get('original_price_inr', current_price))
            
            # Generate historical prices
            historical_prices = self._generate_historical_prices(current_price, product_name, original_price)
            
            self.price_data[key] = {
                'name': product_name,
                'store': store_name,
                'source': 'Local Store',
                'current_price': current_price,
                'original_price': original_price,
                'historical_prices': historical_prices,
                'last_updated': datetime.now()
            }
    
    def _process_flipkart_prices(self, df):
        """Process Flipkart price data"""
        for _, row in df.iterrows():
            product_id = row.get('Uniq Id', '')
            product_name = row.get('Product Title', '')
            
            # Extract price
            price_str = row.get('Price', '0').replace('₹', '').replace(',', '')
            try:
                current_price = float(price_str)
            except:
                continue
            
            # Extract MRP for historical context
            mrp_str = row.get('Mrp', '0').replace('₹', '').replace(',', '')
            try:
                mrp = float(mrp_str)
            except:
                mrp = current_price * 1.2  # Estimate 20% higher MRP
            
            historical_prices = self._generate_historical_prices(current_price, product_name, mrp)
            
            self.price_data[product_id] = {
                'name': product_name,
                'source': 'Flipkart',
                'current_price': current_price,
                'mrp': mrp,
                'historical_prices': historical_prices,
                'last_updated': datetime.now()
            }
    
    def _generate_historical_prices(self, current_price, product_name, original_price=None):
        """Generate realistic historical price data"""
        if original_price is None:
            # Estimate original price (typically 20-50% higher)
            original_price = current_price * np.random.uniform(1.2, 1.5)
        
        # Generate 90 days of historical prices
        days = 90
        prices = []
        
        # Start from original price and trend to current price
        for i in range(days):
            # Calculate progress (0 to 1)
            progress = i / days
            
            # Add random fluctuations
            noise = np.random.normal(0, current_price * 0.02)  # 2% noise
            
            # Simulate price drops and increases
            if progress < 0.3:  # Early period - higher prices
                base_price = original_price * (1 - progress * 0.1)
            elif progress < 0.7:  # Middle period - gradual decrease
                base_price = original_price * (0.9 - (progress - 0.3) * 0.3)
            else:  # Recent period - approach current price
                base_price = original_price * (0.8 - (progress - 0.7) * 0.5)
            
            # Add some random sales/events
            if np.random.random() < 0.1:  # 10% chance of sale
                base_price *= np.random.uniform(0.8, 0.95)  # 5-20% discount
            
            price = max(base_price + noise, current_price * 0.5)  # Don't go too low
            prices.append(price)
        
        # Ensure last price is close to current price
        prices[-1] = current_price
        
        return prices
    
    def prepare_training_data(self):
        """Prepare training data for LSTM"""
        sequences = []
        targets = []
        
        for product_id, data in self.price_data.items():
            prices = data['historical_prices']
            
            if len(prices) < self.sequence_length + self.prediction_days:
                continue
            
            # Create sequences
            for i in range(len(prices) - self.sequence_length - self.prediction_days + 1):
                sequence = prices[i:i + self.sequence_length]
                target = prices[i + self.sequence_length:i + self.sequence_length + self.prediction_days]
                
                sequences.append(sequence)
                targets.append(target)
        
        if not sequences:
            logger.warning("No training data prepared")
            return None, None
        
        # Convert to numpy arrays
        sequences = np.array(sequences)
        targets = np.array(targets)
        
        # Normalize data
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        
        # Fit scaler on all data
        all_prices = np.concatenate([sequences.flatten(), targets.flatten()])
        self.scaler.fit(all_prices.reshape(-1, 1))
        
        # Transform sequences and targets
        sequences_scaled = self.scaler.transform(sequences.reshape(-1, 1)).reshape(sequences.shape)
        targets_scaled = self.scaler.transform(targets.reshape(-1, 1)).reshape(targets.shape)
        
        logger.info(f"Prepared {len(sequences)} training sequences")
        
        return sequences_scaled, targets_scaled
    
    def train(self, epochs=50, batch_size=32):
        """Train the LSTM price prediction model"""
        logger.info("Starting Price Predictor training...")
        
        try:
            # Prepare training data
            sequences, targets = self.prepare_training_data()
            
            if sequences is None:
                logger.error("No training data available")
                return False
            
            # Create dataset and dataloader
            dataset = PriceDataset(sequences, targets)
            dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)
            
            # Create model
            input_size = 1  # Only price as input
            self.model = LSTMPricePredictor(input_size=input_size).to(self.device)
            
            # Loss and optimizer
            criterion = nn.MSELoss()
            optimizer = torch.optim.Adam(self.model.parameters(), lr=0.001)
            
            # Training loop
            self.model.train()
            for epoch in range(epochs):
                total_loss = 0
                
                for batch_sequences, batch_targets in dataloader:
                    batch_sequences = batch_sequences.to(self.device)
                    batch_targets = batch_targets.to(self.device)
                    
                    # Forward pass
                    outputs = self.model(batch_sequences.unsqueeze(-1))  # Add feature dimension
                    loss = criterion(outputs, batch_targets)
                    
                    # Backward pass
                    optimizer.zero_grad()
                    loss.backward()
                    optimizer.step()
                    
                    total_loss += loss.item()
                
                avg_loss = total_loss / len(dataloader)
                
                if epoch % 10 == 0:
                    logger.info(f"Epoch {epoch}, Loss: {avg_loss:.6f}")
            
            # Save model
            self.save_model()
            
            logger.info("Price Predictor training completed successfully!")
            return True
            
        except Exception as e:
            logger.error(f"Error during training: {e}")
            return False
    
    def predict_prices(self, product_id, days_ahead=7):
        """Predict future prices for a product"""
        try:
            if self.model is None:
                self.load_model()
            
            if self.model is None:
                logger.error("Model not available")
                return None
            
            # Get product data
            if product_id not in self.price_data:
                logger.error(f"Product {product_id} not found")
                return None
            
            data = self.price_data[product_id]
            prices = data['historical_prices']
            
            if len(prices) < self.sequence_length:
                logger.error("Insufficient historical data")
                return None
            
            # Prepare input sequence
            input_sequence = prices[-self.sequence_length:]
            input_scaled = self.scaler.transform(np.array(input_sequence).reshape(-1, 1))
            
            # Convert to tensor
            input_tensor = torch.FloatTensor(input_scaled).unsqueeze(0).to(self.device)
            
            # Predict
            self.model.eval()
            with torch.no_grad():
                predictions = []
                current_sequence = input_tensor.clone()
                
                for _ in range(days_ahead):
                    # Predict next price
                    next_price = self.model(current_sequence.unsqueeze(-1))
                    predictions.append(next_price.item())
                    
                    # Update sequence for next prediction
                    next_price_scaled = next_price.unsqueeze(0).unsqueeze(0)
                    current_sequence = torch.cat([current_sequence[:, 1:], next_price_scaled], dim=1)
            
            # Inverse transform to get actual prices
            predictions = np.array(predictions).reshape(-1, 1)
            predictions_actual = self.scaler.inverse_transform(predictions).flatten()
            
            # Generate future dates
            last_date = data['last_updated']
            future_dates = [(last_date + timedelta(days=i+1)).strftime('%Y-%m-%d') for i in range(days_ahead)]
            
            # Calculate confidence intervals (simplified)
            confidence_intervals = []
            for pred in predictions_actual:
                # 5% confidence interval
                lower = pred * 0.95
                upper = pred * 1.05
                confidence_intervals.append((lower, upper))
            
            return {
                'product_id': product_id,
                'product_name': data['name'],
                'current_price': data['current_price'],
                'predictions': predictions_actual.tolist(),
                'dates': future_dates,
                'confidence_intervals': confidence_intervals,
                'trend': self._analyze_trend(predictions_actual),
                'best_day_to_buy': self._find_best_day_to_buy(predictions_actual, future_dates)
            }
            
        except Exception as e:
            logger.error(f"Error predicting prices: {e}")
            return None
    
    def _analyze_trend(self, predictions):
        """Analyze price trend from predictions"""
        if len(predictions) < 2:
            return "insufficient_data"
        
        # Calculate trend
        price_change = predictions[-1] - predictions[0]
        percent_change = (price_change / predictions[0]) * 100
        
        if percent_change > 5:
            return "increasing"
        elif percent_change < -5:
            return "decreasing"
        else:
            return "stable"
    
    def _find_best_day_to_buy(self, predictions, dates):
        """Find the best day to buy based on predictions"""
        if not predictions:
            return None
        
        min_price_idx = np.argmin(predictions)
        best_price = predictions[min_price_idx]
        best_date = dates[min_price_idx]
        
        return {
            'date': best_date,
            'price': best_price,
            'savings': predictions[0] - best_price if predictions else 0
        }
    
    def predict_price_drop_probability(self, product_id, days_ahead=7):
        """Predict probability of price drop"""
        prediction_result = self.predict_prices(product_id, days_ahead)
        
        if not prediction_result:
            return None
        
        predictions = prediction_result['predictions']
        current_price = prediction_result['current_price']
        
        # Count days with price drop
        drop_days = sum(1 for price in predictions if price < current_price)
        probability = drop_days / len(predictions)
        
        return {
            'product_id': product_id,
            'probability_of_drop': probability,
            'expected_drop_amount': current_price - min(predictions),
            'expected_drop_percentage': ((current_price - min(predictions)) / current_price) * 100,
            'recommendation': self._get_buy_recommendation(probability, predictions)
        }
    
    def _get_buy_recommendation(self, probability, predictions):
        """Get buy recommendation based on predictions"""
        if probability > 0.7:
            return "wait_for_drop"
        elif probability > 0.3:
            return "monitor_prices"
        else:
            return "buy_now"
    
    def get_market_insights(self, category=None):
        """Get market price insights"""
        insights = {
            'total_products': len(self.price_data),
            'price_trends': {},
            'best_deals': [],
            'price_drops_predicted': []
        }
        
        # Analyze price trends for sample products
        sample_products = list(self.price_data.keys())[:10]  # Sample first 10
        
        for product_id in sample_products:
            prediction = self.predict_prices(product_id, 7)
            if prediction:
                trend = prediction['trend']
                insights['price_trends'][product_id] = trend
                
                # Check for significant price drops
                if trend == 'decreasing':
                    drop_prob = self.predict_price_drop_probability(product_id)
                    if drop_prob and drop_prob['probability_of_drop'] > 0.5:
                        insights['price_drops_predicted'].append({
                            'product_id': product_id,
                            'product_name': prediction['product_name'],
                            'probability': drop_prob['probability_of_drop'],
                            'expected_drop': drop_prob['expected_drop_percentage']
                        })
        
        return insights
    
    def save_model(self):
        """Save trained model and components"""
        try:
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            
            # Save model
            if self.model:
                torch.save(self.model.state_dict(), self.model_path)
            
            # Save scaler
            if self.scaler:
                with open(self.scaler_path, 'wb') as f:
                    pickle.dump(self.scaler, f)
            
            # Save price data
            with open(self.data_path, 'wb') as f:
                pickle.dump(self.price_data, f)
            
            logger.info(f"Price predictor model saved to {self.model_path}")
            
        except Exception as e:
            logger.error(f"Error saving model: {e}")
    
    def load_model(self):
        """Load trained model and components"""
        try:
            # Load price data
            if os.path.exists(self.data_path):
                with open(self.data_path, 'rb') as f:
                    self.price_data = pickle.load(f)
            
            # Create model
            self.model = LSTMPricePredictor().to(self.device)
            
            # Load model weights
            if os.path.exists(self.model_path):
                self.model.load_state_dict(torch.load(self.model_path, map_location=self.device))
                logger.info(f"Model loaded from {self.model_path}")
            
            # Load scaler
            if os.path.exists(self.scaler_path):
                with open(self.scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
            
            return True
            
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return False


# Example usage
if __name__ == "__main__":
    # Initialize price predictor
    predictor = PricePredictor()
    
    # Train the model
    if predictor.train(epochs=20):
        print("Price predictor trained successfully!")
        
        # Test prediction
        sample_product_id = list(predictor.price_data.keys())[0] if predictor.price_data else None
        
        if sample_product_id:
            # Predict future prices
            prediction = predictor.predict_prices(sample_product_id, days_ahead=7)
            if prediction:
                print(f"\nPrice Prediction for {prediction['product_name']}:")
                print(f"Current Price: ₹{prediction['current_price']:.2f}")
                print(f"Trend: {prediction['trend']}")
                print(f"Best Day to Buy: {prediction['best_day_to_buy']['date']} (₹{prediction['best_day_to_buy']['price']:.2f})")
                
                # Price drop probability
                drop_prob = predictor.predict_price_drop_probability(sample_product_id)
                if drop_prob:
                    print(f"Price Drop Probability: {drop_prob['probability_of_drop']:.1%}")
                    print(f"Recommendation: {drop_prob['recommendation']}")
        
        # Market insights
        insights = predictor.get_market_insights()
        print(f"\nMarket Insights:")
        print(f"Total Products Analyzed: {insights['total_products']}")
        print(f"Products with Predicted Price Drops: {len(insights['price_drops_predicted'])}")
        
    else:
        print("Model training failed!")
