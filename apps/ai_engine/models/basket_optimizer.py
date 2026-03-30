"""
Basket Optimizer for DealSphere
Optimizes shopping basket cost across multiple shops
Suggests split purchase strategies
"""

import pandas as pd
import numpy as np
import itertools
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import pickle
import os

logger = logging.getLogger(__name__)

@dataclass
class Product:
    """Product representation for optimization"""
    name: str
    price: float
    store: str
    category: str
    distance: float
    delivery_time: float
    reliability: float
    quantity: int = 1

@dataclass
class OptimizationResult:
    """Result of basket optimization"""
    total_cost: float
    stores: List[str]
    products_by_store: Dict[str, List[Product]]
    savings: float
    delivery_cost: float
    time_cost: float
    strategy: str

class BasketOptimizer:
    """
    Shopping basket optimization system
    Uses combinatorial optimization to find best purchase strategy
    """
    
    def __init__(self, model_path=None):
        self.model_path = model_path or 'ai_engine/models/ranking_engine/model_weights/optimizer_model.pkl'
        self.delivery_rates = {
            'same_day': 50,
            'next_day': 30,
            'standard': 0,
            'pickup': 0
        }
        self.time_value_per_hour = 100  # Value of user's time per hour
        
        # Load product data
        self.load_product_data()
    
    def load_product_data(self):
        """Load product data from real datasets"""
        try:
            # Load Amazon dataset
            amazon_path = 'dataset/amazon.csv'
            self.amazon_df = pd.read_csv(amazon_path)
            
            # Load local stores dataset
            local_path = 'dataset/local_store_offer_dataset.csv'
            self.local_df = pd.read_csv(local_path)
            
            # Load Flipkart dataset
            flipkart_path = 'dataset/marketing_sample_for_flipkart_com-ecommerce__20191101_20191130__15k_data.csv'
            self.flipkart_df = pd.read_csv(flipkart_path)
            
            logger.info("Loaded product datasets for basket optimization")
            
        except Exception as e:
            logger.error(f"Error loading product data: {e}")
            self.amazon_df = pd.DataFrame()
            self.local_df = pd.DataFrame()
            self.flipkart_df = pd.DataFrame()
    
    def find_product_variants(self, product_name: str, quantity: int = 1) -> List[Product]:
        """Find all variants of a product across different stores"""
        variants = []
        
        try:
            # Search in Amazon
            amazon_matches = self.amazon_df[
                self.amazon_df['product_name'].str.contains(product_name, case=False, na=False)
            ]
            
            for _, row in amazon_matches.iterrows():
                price_str = row.get('discounted_price', '₹0').replace('₹', '').replace(',', '')
                try:
                    price = float(price_str)
                except:
                    price = 0
                
                variants.append(Product(
                    name=row.get('product_name', ''),
                    price=price,
                    store='Amazon',
                    category=row.get('category', ''),
                    distance=np.random.uniform(5, 50),  # Simulated distance
                    delivery_time=np.random.uniform(2, 7),  # 2-7 days
                    reliability=0.9,  # High reliability for Amazon
                    quantity=quantity
                ))
            
            # Search in local stores
            local_matches = self.local_df[
                self.local_df['product_name'].str.contains(product_name, case=False, na=False)
            ]
            
            for _, row in local_matches.iterrows():
                price = float(row.get('offer_price_inr', 0))
                store_name = row.get('store_name', 'Local Store')
                
                variants.append(Product(
                    name=row.get('product_name', ''),
                    price=price,
                    store=store_name,
                    category=row.get('product_category', ''),
                    distance=np.random.uniform(0.5, 10),  # Closer for local
                    delivery_time=np.random.uniform(0.5, 2),  # Same-day or next-day
                    reliability=0.8,  # Good reliability for local stores
                    quantity=quantity
                ))
            
            # Search in Flipkart
            flipkart_matches = self.flipkart_df[
                self.flipkart_df['Product Title'].str.contains(product_name, case=False, na=False)
            ]
            
            for _, row in flipkart_matches.iterrows():
                price_str = row.get('Price', '0').replace('₹', '').replace(',', '')
                try:
                    price = float(price_str)
                except:
                    price = 0
                
                variants.append(Product(
                    name=row.get('Product Title', ''),
                    price=price,
                    store='Flipkart',
                    category=row.get('Bb Category', ''),
                    distance=np.random.uniform(5, 50),
                    delivery_time=np.random.uniform(3, 7),
                    reliability=0.85,
                    quantity=quantity
                ))
            
        except Exception as e:
            logger.error(f"Error finding product variants: {e}")
        
        return variants
    
    def calculate_delivery_cost(self, products: List[Product]) -> float:
        """Calculate total delivery cost for a set of products"""
        if not products:
            return 0
        
        # Group by store
        stores = {}
        for product in products:
            if product.store not in stores:
                stores[product.store] = []
            stores[product.store].append(product)
        
        total_delivery_cost = 0
        
        for store, store_products in stores.items():
            # Determine delivery type based on delivery_time
            avg_delivery_time = np.mean([p.delivery_time for p in store_products])
            
            if avg_delivery_time <= 0.5:  # Same day
                delivery_type = 'same_day'
            elif avg_delivery_time <= 1:  # Next day
                delivery_type = 'next_day'
            else:  # Standard
                delivery_type = 'standard'
            
            # Apply delivery cost (per store, not per product)
            total_delivery_cost += self.delivery_rates[delivery_type]
        
        return total_delivery_cost
    
    def calculate_time_cost(self, products: List[Product]) -> float:
        """Calculate time cost based on delivery time"""
        if not products:
            return 0
        
        total_time = 0
        for product in products:
            # Calculate time cost based on delivery time
            if product.delivery_time <= 0.5:  # Same day - no time cost
                time_cost = 0
            elif product.delivery_time <= 1:  # Next day - minimal time cost
                time_cost = self.time_value_per_hour * 0.5
            else:  # Standard delivery - higher time cost
                time_cost = self.time_value_per_hour * (product.delivery_time / 24)
            
            total_time += time_cost
        
        return total_time
    
    def calculate_total_cost(self, products: List[Product]) -> float:
        """Calculate total cost including product price, delivery, and time cost"""
        product_cost = sum(p.price * p.quantity for p in products)
        delivery_cost = self.calculate_delivery_cost(products)
        time_cost = self.calculate_time_cost(products)
        
        return product_cost + delivery_cost + time_cost
    
    def optimize_single_store(self, product_list: List[str], quantities: List[int]) -> OptimizationResult:
        """Optimize by buying everything from single best store"""
        best_result = None
        best_cost = float('inf')
        
        stores = ['Amazon', 'Flipkart', 'Local Store']
        
        for store in stores:
            store_products = []
            total_product_cost = 0
            
            for product_name, quantity in zip(product_list, quantities):
                variants = self.find_product_variants(product_name, quantity)
                
                # Find cheapest variant from this store
                store_variants = [v for v in variants if v.store == store]
                
                if store_variants:
                    cheapest = min(store_variants, key=lambda x: x.price)
                    store_products.append(cheapest)
                    total_product_cost += cheapest.price * quantity
                else:
                    # Product not available in this store
                    total_product_cost = float('inf')
                    break
            
            if total_product_cost < float('inf'):
                delivery_cost = self.calculate_delivery_cost(store_products)
                time_cost = self.calculate_time_cost(store_products)
                total_cost = total_product_cost + delivery_cost + time_cost
                
                if total_cost < best_cost:
                    best_cost = total_cost
                    best_result = OptimizationResult(
                        total_cost=total_cost,
                        stores=[store],
                        products_by_store={store: store_products},
                        savings=0,  # Will be calculated later
                        delivery_cost=delivery_cost,
                        time_cost=time_cost,
                        strategy=f"Single Store ({store})"
                    )
        
        return best_result
    
    def optimize_split_purchase(self, product_list: List[str], quantities: List[int]) -> OptimizationResult:
        """Optimize by splitting purchase across multiple stores"""
        all_combinations = []
        
        # Generate all possible store combinations for each product
        product_options = []
        for product_name, quantity in zip(product_list, quantities):
            variants = self.find_product_variants(product_name, quantity)
            if variants:
                product_options.append(variants)
            else:
                # Create dummy product if not found
                dummy = Product(
                    name=product_name,
                    price=999999,  # Very high price to discourage selection
                    store='Unknown',
                    category='Unknown',
                    distance=100,
                    delivery_time=7,
                    reliability=0.1,
                    quantity=quantity
                )
                product_options.append([dummy])
        
        # Try different split strategies
        strategies = [
            self._split_by_category,
            self._split_by_price,
            self._split_by_delivery,
            self._split_optimal
        ]
        
        best_result = None
        best_cost = float('inf')
        
        for strategy in strategies:
            try:
                result = strategy(product_options)
                if result and result.total_cost < best_cost:
                    best_cost = result.total_cost
                    best_result = result
            except Exception as e:
                logger.error(f"Error in strategy {strategy.__name__}: {e}")
                continue
        
        return best_result
    
    def _split_by_category(self, product_options: List[List[Product]]) -> OptimizationResult:
        """Split by product categories"""
        category_groups = {}
        
        for options in product_options:
            if not options:
                continue
            
            # Choose cheapest option for each product
            cheapest = min(options, key=lambda x: x.price)
            category = cheapest.category
            
            if category not in category_groups:
                category_groups[category] = []
            category_groups[category].append(cheapest)
        
        # Calculate costs
        all_products = []
        for products in category_groups.values():
            all_products.extend(products)
        
        total_cost = self.calculate_total_cost(all_products)
        delivery_cost = self.calculate_delivery_cost(all_products)
        time_cost = self.calculate_time_cost(all_products)
        
        return OptimizationResult(
            total_cost=total_cost,
            stores=list(set(p.store for p in all_products)),
            products_by_store=self._group_by_store(all_products),
            savings=0,
            delivery_cost=delivery_cost,
            time_cost=time_cost,
            strategy="Split by Category"
        )
    
    def _split_by_price(self, product_options: List[List[Product]]) -> OptimizationResult:
        """Split by price ranges (cheap vs expensive)"""
        cheap_products = []
        expensive_products = []
        
        for options in product_options:
            if not options:
                continue
            
            cheapest = min(options, key=lambda x: x.price)
            
            if cheapest.price < 500:  # Threshold for cheap products
                cheap_products.append(cheapest)
            else:
                expensive_products.append(cheapest)
        
        all_products = cheap_products + expensive_products
        total_cost = self.calculate_total_cost(all_products)
        delivery_cost = self.calculate_delivery_cost(all_products)
        time_cost = self.calculate_time_cost(all_products)
        
        return OptimizationResult(
            total_cost=total_cost,
            stores=list(set(p.store for p in all_products)),
            products_by_store=self._group_by_store(all_products),
            savings=0,
            delivery_cost=delivery_cost,
            time_cost=time_cost,
            strategy="Split by Price"
        )
    
    def _split_by_delivery(self, product_options: List[List[Product]]) -> OptimizationResult:
        """Split by delivery time (urgent vs standard)"""
        urgent_products = []
        standard_products = []
        
        for options in product_options:
            if not options:
                continue
            
            # Choose fastest delivery
            fastest = min(options, key=lambda x: x.delivery_time)
            
            if fastest.delivery_time <= 1:  # Urgent (same/next day)
                urgent_products.append(fastest)
            else:  # Standard delivery
                standard_products.append(fastest)
        
        all_products = urgent_products + standard_products
        total_cost = self.calculate_total_cost(all_products)
        delivery_cost = self.calculate_delivery_cost(all_products)
        time_cost = self.calculate_time_cost(all_products)
        
        return OptimizationResult(
            total_cost=total_cost,
            stores=list(set(p.store for p in all_products)),
            products_by_store=self._group_by_store(all_products),
            savings=0,
            delivery_cost=delivery_cost,
            time_cost=time_cost,
            strategy="Split by Delivery Time"
        )
    
    def _split_optimal(self, product_options: List[List[Product]]) -> OptimizationResult:
        """Optimal split using combinatorial optimization"""
        best_combination = None
        best_cost = float('inf')
        
        # For small baskets, try all combinations
        if len(product_options) <= 5:
            all_combinations = list(itertools.product(*product_options))
            
            # Sample combinations to avoid excessive computation
            sample_size = min(1000, len(all_combinations))
            sampled_combinations = all_combinations[:sample_size]
            
            for combination in sampled_combinations:
                total_cost = self.calculate_total_cost(list(combination))
                
                if total_cost < best_cost:
                    best_cost = total_cost
                    best_combination = combination
        else:
            # For large baskets, use greedy approach
            best_combination = []
            for options in product_options:
                if options:
                    # Choose cheapest option considering delivery
                    best_option = min(options, key=lambda x: x.price + self.calculate_delivery_cost([x]))
                    best_combination.append(best_option)
            
            best_cost = self.calculate_total_cost(best_combination)
        
        if best_combination:
            delivery_cost = self.calculate_delivery_cost(list(best_combination))
            time_cost = self.calculate_time_cost(list(best_combination))
            
            return OptimizationResult(
                total_cost=best_cost,
                stores=list(set(p.store for p in best_combination)),
                products_by_store=self._group_by_store(list(best_combination)),
                savings=0,
                delivery_cost=delivery_cost,
                time_cost=time_cost,
                strategy="Optimal Split"
            )
        
        return None
    
    def _group_by_store(self, products: List[Product]) -> Dict[str, List[Product]]:
        """Group products by store"""
        store_groups = {}
        for product in products:
            if product.store not in store_groups:
                store_groups[product.store] = []
            store_groups[product.store].append(product)
        return store_groups
    
    def optimize_basket(self, product_list: List[str], quantities: List[int], budget: Optional[float] = None) -> Dict:
        """Main optimization function"""
        try:
            if len(product_list) != len(quantities):
                raise ValueError("Product list and quantities must have same length")
            
            # Calculate baseline (single cheapest store)
            baseline_result = self.optimize_single_store(product_list, quantities)
            
            # Calculate split purchase options
            split_result = self.optimize_split_purchase(product_list, quantities)
            
            # Compare results
            results = []
            
            if baseline_result:
                results.append(baseline_result)
            
            if split_result:
                results.append(split_result)
            
            # Sort by total cost
            results.sort(key=lambda x: x.total_cost)
            
            # Calculate savings
            if len(results) > 1:
                baseline_cost = results[-1].total_cost  # Worst option
                for result in results:
                    result.savings = baseline_cost - result.total_cost
            
            # Filter by budget if provided
            if budget:
                affordable_results = [r for r in results if r.total_cost <= budget]
                if affordable_results:
                    results = affordable_results
            
            return {
                'best_option': results[0] if results else None,
                'all_options': results,
                'baseline_cost': baseline_result.total_cost if baseline_result else 0,
                'max_savings': max([r.savings for r in results]) if results else 0,
                'product_count': len(product_list),
                'budget': budget,
                'within_budget': results[0].total_cost <= budget if results and budget else None
            }
            
        except Exception as e:
            logger.error(f"Error optimizing basket: {e}")
            return {
                'error': str(e),
                'best_option': None,
                'all_options': []
            }
    
    def generate_recommendations(self, optimization_result: Dict) -> List[str]:
        """Generate human-readable recommendations"""
        recommendations = []
        
        if not optimization_result.get('best_option'):
            return ["No optimization results available"]
        
        best = optimization_result['best_option']
        
        # Main recommendation
        recommendations.append(f"Best strategy: {best.strategy}")
        recommendations.append(f"Total cost: ₹{best.total_cost:.2f}")
        
        # Store breakdown
        if len(best.stores) == 1:
            recommendations.append(f"Buy everything from {best.stores[0]}")
        else:
            recommendations.append(f"Split purchase across {len(best.stores)} stores:")
            for store, products in best.products_by_store.items():
                store_cost = sum(p.price * p.quantity for p in products)
                recommendations.append(f"  • {store}: ₹{store_cost:.2f} ({len(products)} items)")
        
        # Savings information
        if best.savings > 0:
            recommendations.append(f"You'll save ₹{best.savings:.2f} compared to other options")
        
        # Delivery information
        if best.delivery_cost > 0:
            recommendations.append(f"Delivery cost: ₹{best.delivery_cost:.2f}")
        else:
            recommendations.append("Free delivery")
        
        # Budget information
        budget = optimization_result.get('budget')
        if budget:
            if best.total_cost <= budget:
                recommendations.append(f"Within your ₹{budget:.2f} budget")
            else:
                recommendations.append(f"Exceeds budget by ₹{best.total_cost - budget:.2f}")
        
        return recommendations
    
    def save_model(self):
        """Save optimization model configuration"""
        try:
            config = {
                'delivery_rates': self.delivery_rates,
                'time_value_per_hour': self.time_value_per_hour
            }
            
            os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
            with open(self.model_path, 'wb') as f:
                pickle.dump(config, f)
            
            logger.info(f"Basket optimizer configuration saved to {self.model_path}")
            
        except Exception as e:
            logger.error(f"Error saving model: {e}")
    
    def load_model(self):
        """Load optimization model configuration"""
        try:
            if os.path.exists(self.model_path):
                with open(self.model_path, 'rb') as f:
                    config = pickle.load(f)
                    self.delivery_rates = config.get('delivery_rates', self.delivery_rates)
                    self.time_value_per_hour = config.get('time_value_per_hour', self.time_value_per_hour)
                
                logger.info(f"Basket optimizer configuration loaded from {self.model_path}")
                return True
            else:
                logger.info("No saved configuration found, using defaults")
                return True
                
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return False


# Example usage
if __name__ == "__main__":
    # Initialize basket optimizer
    optimizer = BasketOptimizer()
    
    # Test optimization
    shopping_list = ["USB Cable", "Smartphone", "Lipstick"]
    quantities = [2, 1, 3]
    budget = 10000
    
    result = optimizer.optimize_basket(shopping_list, quantities, budget)
    
    print("Basket Optimization Results:")
    print(f"Best Option: {result['best_option'].strategy if result['best_option'] else 'None'}")
    print(f"Total Cost: ₹{result['best_option'].total_cost:.2f}" if result['best_option'] else "N/A")
    print(f"Max Savings: ₹{result['max_savings']:.2f}")
    
    # Generate recommendations
    recommendations = optimizer.generate_recommendations(result)
    print("\nRecommendations:")
    for rec in recommendations:
        print(f"• {rec}")
