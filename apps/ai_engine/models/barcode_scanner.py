"""
Barcode Scanner Logic for DealSphere
Matches barcode numbers to products using real datasets
"""

import pandas as pd
import numpy as np
import re
import pickle
import os
import logging
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class BarcodeScanner:
    """
    Barcode scanning and product matching system
    """
    
    def __init__(self, database_path=None):
        self.barcode_database = {}
        self.product_database = {}
        self.database_path = database_path or 'ai_engine/models/barcode_scanner/model_weights/barcode_database.pkl'
        
        # Load product data
        self.load_product_data()
        
    def load_product_data(self):
        """Load product data from real datasets"""
        try:
            # Load Amazon dataset
            amazon_path = 'dataset/raw/amazon.csv'
            amazon_df = pd.read_csv(amazon_path)
            
            # Load Flipkart dataset
            flipkart_path = 'dataset/raw/marketing_sample_for_flipkart_com-ecommerce__20191101_20191130__15k_data.csv'
            flipkart_df = pd.read_csv(flipkart_path)
            
            # Load local stores dataset
            local_path = 'dataset/raw/local_store_offer_dataset.csv'
            local_df = pd.read_csv(local_path)
            
            # Build product database
            self._build_amazon_database(amazon_df)
            self._build_flipkart_database(flipkart_df)
            self._build_local_database(local_df)
            
            # Generate synthetic barcodes for products without them
            self._generate_barcodes()
            
            # Save database
            self.save_database()
            
            logger.info(f"Loaded {len(self.product_database)} products in barcode database")
            
        except Exception as e:
            logger.error(f"Error loading product data: {e}")
    
    def _build_amazon_database(self, df):
        """Build database from Amazon dataset"""
        for _, row in df.iterrows():
            product_id = row.get('product_id', '')
            product_name = row.get('product_name', '')
            category = row.get('category', '')
            brand = self._extract_brand(product_name)
            
            # Extract price
            price_str = row.get('discounted_price', '₹0').replace('₹', '').replace(',', '')
            try:
                price = float(price_str)
            except:
                price = 0
            
            # Generate barcode from product ID or create synthetic one
            barcode = self._generate_barcode_from_id(product_id)
            
            self.barcode_database[barcode] = {
                'product_id': product_id,
                'name': product_name,
                'brand': brand,
                'category': category,
                'price': price,
                'rating': row.get('rating', ''),
                'source': 'Amazon',
                'image_url': row.get('img_link', ''),
                'product_url': row.get('product_link', '')
            }
            
            # Also index by product name for fuzzy matching
            name_key = self._normalize_name(product_name)
            if name_key not in self.product_database:
                self.product_database[name_key] = []
            self.product_database[name_key].append(self.barcode_database[barcode])
    
    def _build_flipkart_database(self, df):
        """Build database from Flipkart dataset"""
        for _, row in df.iterrows():
            product_id = row.get('Uniq Id', '')
            product_name = row.get('Product Title', '')
            category = row.get('Bb Category', '')
            brand = self._extract_brand(product_name)
            
            # Extract price
            price_str = row.get('Price', '0').replace('₹', '').replace(',', '')
            try:
                price = float(price_str)
            except:
                price = 0
            
            # Generate barcode
            barcode = self._generate_barcode_from_id(product_id)
            
            self.barcode_database[barcode] = {
                'product_id': product_id,
                'name': product_name,
                'brand': brand,
                'category': category,
                'price': price,
                'source': 'Flipkart',
                'image_url': row.get('Image Url', ''),
                'product_url': row.get('Url', '')
            }
            
            # Index by name
            name_key = self._normalize_name(product_name)
            if name_key not in self.product_database:
                self.product_database[name_key] = []
            self.product_database[name_key].append(self.barcode_database[barcode])
    
    def _build_local_database(self, df):
        """Build database from local stores dataset"""
        for _, row in df.iterrows():
            product_name = row.get('product_name', '')
            category = row.get('product_category', '')
            brand = row.get('brand', '')
            store = row.get('store_name', '')
            
            price = float(row.get('offer_price_inr', 0))
            
            # Generate barcode
            barcode = self._generate_barcode_from_name(product_name, store)
            
            self.barcode_database[barcode] = {
                'product_id': f"LOCAL_{len(self.barcode_database)}",
                'name': product_name,
                'brand': brand,
                'category': category,
                'price': price,
                'store': store,
                'source': 'Local Store',
                'discount': row.get('discount_percent', 0),
                'offer_end_date': row.get('offer_end_date', '')
            }
            
            # Index by name
            name_key = self._normalize_name(product_name)
            if name_key not in self.product_database:
                self.product_database[name_key] = []
            self.product_database[name_key].append(self.barcode_database[barcode])
    
    def _extract_brand(self, product_name):
        """Extract brand name from product title"""
        # Common brand names from datasets
        common_brands = [
            'Samsung', 'Apple', 'Nike', 'Adidas', 'Sony', 'LG', 'HP', 'Dell',
            'Boat', 'Ambrane', 'Portronics', 'pTron', 'Wayona', 'Sounce',
            'MI', 'TP-Link', 'B Natural', 'Parle', 'Whiskas', 'Enchanteur'
        ]
        
        product_name_upper = product_name.upper()
        
        for brand in common_brands:
            if brand.upper() in product_name_upper:
                return brand
        
        # Try to extract first word as brand
        words = product_name.split()
        if words:
            return words[0]
        
        return 'Unknown'
    
    def _normalize_name(self, name):
        """Normalize product name for matching"""
        # Remove special characters, convert to lowercase
        normalized = re.sub(r'[^a-zA-Z0-9\s]', '', name.lower())
        # Remove extra spaces
        normalized = ' '.join(normalized.split())
        return normalized
    
    def _generate_barcode_from_id(self, product_id):
        """Generate barcode from product ID"""
        if not product_id:
            return self._generate_random_barcode()
        
        # Convert product ID to numeric barcode
        # Remove non-alphanumeric characters
        clean_id = re.sub(r'[^a-zA-Z0-9]', '', product_id)
        
        # Convert to number
        if clean_id:
            # Simple hash to generate consistent barcode
            barcode_hash = hash(clean_id) % (10**12)  # 12-digit barcode
            return f"{barcode_hash:012d}"
        else:
            return self._generate_random_barcode()
    
    def _generate_barcode_from_name(self, product_name, store=''):
        """Generate barcode from product name and store"""
        combined = f"{product_name}_{store}"
        return self._generate_barcode_from_id(combined)
    
    def _generate_random_barcode(self):
        """Generate random 13-digit barcode"""
        import random
        return ''.join([str(random.randint(0, 9)) for _ in range(13)])
    
    def _generate_barcodes(self):
        """Generate synthetic barcodes for products without them"""
        # This is already handled in the build methods above
        pass
    
    def scan_barcode(self, barcode_number):
        """Scan barcode and return product information"""
        try:
            # Clean barcode number
            clean_barcode = re.sub(r'[^0-9]', '', barcode_number)
            
            if not clean_barcode:
                return None
            
            # Direct barcode lookup
            if clean_barcode in self.barcode_database:
                product = self.barcode_database[clean_barcode]
                return {
                    'found': True,
                    'match_type': 'exact',
                    'product': product,
                    'barcode': clean_barcode
                }
            
            # Try partial match (first 8 digits)
            if len(clean_barcode) >= 8:
                partial = clean_barcode[:8]
                for barcode, product in self.barcode_database.items():
                    if barcode.startswith(partial):
                        return {
                            'found': True,
                            'match_type': 'partial',
                            'product': product,
                            'barcode': barcode,
                            'confidence': 0.8
                        }
            
            # No match found
            return {
                'found': False,
                'barcode': clean_barcode,
                'message': 'Barcode not found in database'
            }
            
        except Exception as e:
            logger.error(f"Error scanning barcode: {e}")
            return {
                'found': False,
                'error': str(e)
            }
    
    def search_by_name(self, product_name, top_k=5):
        """Search products by name using fuzzy matching"""
        try:
            normalized_query = self._normalize_name(product_name)
            
            matches = []
            
            for name_key, products in self.product_database.items():
                # Calculate similarity
                similarity = SequenceMatcher(None, normalized_query, name_key).ratio()
                
                if similarity > 0.3:  # Threshold for matching
                    for product in products:
                        matches.append({
                            'product': product,
                            'similarity': similarity,
                            'match_type': 'name_fuzzy'
                        })
            
            # Sort by similarity
            matches.sort(key=lambda x: x['similarity'], reverse=True)
            
            # Return top matches
            return matches[:top_k]
            
        except Exception as e:
            logger.error(f"Error searching by name: {e}")
            return []
    
    def get_similar_products(self, barcode, top_k=5):
        """Get similar products based on barcode"""
        try:
            # Find product by barcode
            scan_result = self.scan_barcode(barcode)
            
            if not scan_result['found']:
                return []
            
            product = scan_result['product']
            category = product.get('category', '').lower()
            brand = product.get('brand', '').lower()
            
            similar_products = []
            
            # Find products in same category or brand
            for other_barcode, other_product in self.barcode_database.items():
                if other_barcode == barcode:
                    continue
                
                similarity_score = 0
                
                # Category match
                if category and category in other_product.get('category', '').lower():
                    similarity_score += 0.5
                
                # Brand match
                if brand and brand in other_product.get('brand', '').lower():
                    similarity_score += 0.3
                
                # Name similarity
                name_similarity = SequenceMatcher(
                    None, 
                    self._normalize_name(product.get('name', '')),
                    self._normalize_name(other_product.get('name', ''))
                ).ratio()
                similarity_score += name_similarity * 0.2
                
                if similarity_score > 0.3:
                    similar_products.append({
                        'product': other_product,
                        'similarity': similarity_score,
                        'barcode': other_barcode
                    })
            
            # Sort by similarity
            similar_products.sort(key=lambda x: x['similarity'], reverse=True)
            
            return similar_products[:top_k]
            
        except Exception as e:
            logger.error(f"Error getting similar products: {e}")
            return []
    
    def compare_prices(self, barcode):
        """Compare prices for the same product across different sources"""
        try:
            scan_result = self.scan_barcode(barcode)
            
            if not scan_result['found']:
                return []
            
            product = scan_result['product']
            product_name = product.get('name', '')
            
            # Search for same product from other sources
            name_matches = self.search_by_name(product_name, top_k=20)
            
            # Group by product name
            price_comparison = {}
            
            for match in name_matches:
                match_product = match['product']
                name = match_product.get('name', '')
                source = match_product.get('source', '')
                price = match_product.get('price', 0)
                
                if name not in price_comparison:
                    price_comparison[name] = []
                
                price_comparison[name].append({
                    'source': source,
                    'price': price,
                    'product': match_product,
                    'similarity': match['similarity']
                })
            
            # Find best prices
            results = []
            for name, variants in price_comparison.items():
                if len(variants) > 1:  # Product available from multiple sources
                    # Sort by price
                    variants.sort(key=lambda x: x['price'])
                    
                    results.append({
                        'product_name': name,
                        'variants': variants,
                        'best_price': variants[0]['price'],
                        'best_source': variants[0]['source'],
                        'price_range': {
                            'min': variants[0]['price'],
                            'max': variants[-1]['price']
                        }
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"Error comparing prices: {e}")
            return []
    
    def generate_barcode_image(self, barcode_number):
        """Generate barcode image (placeholder)"""
        # In real implementation, would use barcode generation library
        return {
            'barcode': barcode_number,
            'image_url': f'/barcode/{barcode_number}.png',
            'format': 'CODE128'
        }
    
    def save_database(self):
        """Save barcode database to file"""
        try:
            os.makedirs(os.path.dirname(self.database_path), exist_ok=True)
            
            with open(self.database_path, 'wb') as f:
                pickle.dump({
                    'barcode_database': self.barcode_database,
                    'product_database': self.product_database
                }, f)
            
            logger.info(f"Barcode database saved to {self.database_path}")
            
        except Exception as e:
            logger.error(f"Error saving database: {e}")
    
    def load_database(self):
        """Load barcode database from file"""
        try:
            if os.path.exists(self.database_path):
                with open(self.database_path, 'rb') as f:
                    data = pickle.load(f)
                    self.barcode_database = data.get('barcode_database', {})
                    self.product_database = data.get('product_database', {})
                
                logger.info(f"Barcode database loaded from {self.database_path}")
                return True
            else:
                logger.info("Barcode database not found, creating new one")
                self.load_product_data()
                return True
                
        except Exception as e:
            logger.error(f"Error loading database: {e}")
            return False
    
    def get_statistics(self):
        """Get database statistics"""
        stats = {
            'total_products': len(self.barcode_database),
            'sources': {},
            'categories': {},
            'brands': {}
        }
        
        for product in self.barcode_database.values():
            # Count by source
            source = product.get('source', 'Unknown')
            stats['sources'][source] = stats['sources'].get(source, 0) + 1
            
            # Count by category
            category = product.get('category', 'Unknown')
            stats['categories'][category] = stats['categories'].get(category, 0) + 1
            
            # Count by brand
            brand = product.get('brand', 'Unknown')
            stats['brands'][brand] = stats['brands'].get(brand, 0) + 1
        
        return stats


# Example usage
if __name__ == "__main__":
    # Initialize barcode scanner
    scanner = BarcodeScanner()
    
    # Load database
    scanner.load_database()
    
    # Test barcode scanning
    test_barcodes = [
        '1234567890123',  # Random barcode
        'B07JW9H4J1',     # Amazon product ID style
        '0633d9fd9a3271730fae687f105c7a3a'  # Flipkart ID style
    ]
    
    for barcode in test_barcodes:
        result = scanner.scan_barcode(barcode)
        print(f"\nBarcode: {barcode}")
        print(f"Result: {result}")
    
    # Test name search
    name_result = scanner.search_by_name("USB Cable", top_k=3)
    print(f"\nName search for 'USB Cable':")
    for match in name_result:
        print(f"  {match['product']['name']} - Similarity: {match['similarity']:.2f}")
    
    # Show statistics
    stats = scanner.get_statistics()
    print(f"\nDatabase Statistics:")
    print(f"Total Products: {stats['total_products']}")
    print(f"Sources: {stats['sources']}")
