#!/usr/bin/env python3
"""
Automatic Product Mapping Script for Syrve Integration

This script automatically maps local products from base_products.csv to Syrve API products
by fetching the complete Syrve product catalog and using fuzzy matching algorithms.
"""

import csv
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from difflib import SequenceMatcher
import re
import sys
import os

sys.path.append(str(Path(__file__).parent.parent))

from app.services.unified_syrve_client import UnifiedSyrveClient
from app.config import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ProductMatcher:
    def __init__(self):
        self.syrve_client = UnifiedSyrveClient(
            base_url=settings.SYRVE_SERVER_URL,
            login=settings.SYRVE_LOGIN,
            password=settings.SYRVE_PASSWORD,
            verify_ssl=settings.VERIFY_SSL
        )
        self.syrve_products: List[Dict] = []
        self.local_products: List[Dict] = []
        
    def normalize_name(self, name: str) -> str:
        """Normalize product name for better matching"""
        if not name:
            return ""
        
        # Convert to lowercase
        normalized = name.lower().strip()
        
        # Remove special characters and extra spaces
        normalized = re.sub(r'[^\w\s]', ' ', normalized)
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Common substitutions for better matching
        substitutions = {
            'моцарелла': 'mozzarella',
            'майонез': 'mayo',
            'майо': 'mayo',
            'сыр': 'cheese',
            'мясо': 'meat',
            'курица': 'chicken',
            'говядина': 'beef',
            'свинина': 'pork',
            'томат': 'tomato',
            'помидор': 'tomato',
            'лук': 'onion',
            'грибы': 'mushrooms',
            'перец': 'pepper',
            'салат': 'salad',
            'огурец': 'cucumber',
            'морковь': 'carrot',
        }
        
        for ru, en in substitutions.items():
            if ru in normalized:
                normalized = normalized.replace(ru, en)
                
        return normalized.strip()
    
    def calculate_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two product names"""
        norm1 = self.normalize_name(name1)
        norm2 = self.normalize_name(name2)
        
        if not norm1 or not norm2:
            return 0.0
            
        # Exact match after normalization
        if norm1 == norm2:
            return 1.0
            
        # Sequence matcher for overall similarity
        seq_similarity = SequenceMatcher(None, norm1, norm2).ratio()
        
        # Check for substring matches
        if norm1 in norm2 or norm2 in norm1:
            seq_similarity = max(seq_similarity, 0.8)
            
        # Word-based matching
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        
        if words1 and words2:
            word_intersection = len(words1.intersection(words2))
            word_union = len(words1.union(words2))
            word_similarity = word_intersection / word_union if word_union > 0 else 0
            
            # Combine similarities with weights
            combined_similarity = 0.7 * seq_similarity + 0.3 * word_similarity
            return min(combined_similarity, 1.0)
            
        return seq_similarity
    
    async def fetch_syrve_products(self) -> bool:
        """Fetch all products from Syrve API"""
        try:
            logger.info("Fetching products from Syrve API...")
            
            # Get auth token first
            token = await self.syrve_client.get_token_async()
            if not token:
                logger.error("Failed to get auth token")
                return False
            
            # Fetch products using direct API call
            import httpx
            url = f"{settings.SYRVE_SERVER_URL}/resto/api/products?key={token}"
            
            async with httpx.AsyncClient(verify=settings.VERIFY_SSL, timeout=30) as client:
                response = await client.get(url)
                
                logger.info(f"Response status: {response.status_code}")
                logger.info(f"Response content type: {response.headers.get('content-type')}")
                logger.info(f"Response first 200 chars: {response.text[:200]}")
                
                if response.status_code != 200:
                    logger.error(f"Failed to fetch products: {response.status_code}")
                    return False
                
                # Try to parse as XML first (Syrve often returns XML)
                try:
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(response.text)
                    
                    # Extract products from XML - look for productDto elements
                    products_data = []
                    for product in root.findall('.//productDto'):
                        product_id = product.find('id')
                        product_name = product.find('name')
                        
                        if product_id is not None and product_name is not None:
                            product_dict = {
                                'id': product_id.text,
                                'name': product_name.text,
                            }
                            products_data.append(product_dict)
                    
                    logger.info(f"Parsed {len(products_data)} products from XML")
                    
                except ET.ParseError:
                    # If XML parsing fails, try JSON
                    try:
                        products_data = response.json()
                        logger.info(f"Parsed {len(products_data)} products from JSON")
                    except ValueError as e:
                        logger.error(f"Failed to parse response as XML or JSON: {e}")
                        return False
                
                if not products_data:
                    logger.error("No products received from Syrve API")
                    return False
                    
                self.syrve_products = products_data
                logger.info(f"Successfully fetched {len(self.syrve_products)} products from Syrve")
                return True
            
        except Exception as e:
            logger.error(f"Error fetching Syrve products: {e}")
            return False
    
    def load_local_products(self, csv_path: str) -> bool:
        """Load local products from CSV file"""
        try:
            logger.info(f"Loading local products from {csv_path}")
            
            with open(csv_path, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                self.local_products = list(reader)
                
            logger.info(f"Loaded {len(self.local_products)} local products")
            return True
            
        except Exception as e:
            logger.error(f"Error loading local products: {e}")
            return False
    
    def find_best_match(self, local_product: Dict) -> Optional[Tuple[Dict, float]]:
        """Find the best matching Syrve product for a local product"""
        local_name = local_product.get('name', '')
        if not local_name:
            return None
            
        best_match = None
        best_score = 0.0
        
        for syrve_product in self.syrve_products:
            syrve_name = syrve_product.get('name', '')
            if not syrve_name:
                continue
                
            similarity = self.calculate_similarity(local_name, syrve_name)
            
            if similarity > best_score:
                best_score = similarity
                best_match = syrve_product
                
        return (best_match, best_score) if best_match and best_score >= 0.6 else None
    
    def generate_mappings(self) -> Tuple[List[Dict], List[Dict]]:
        """Generate product mappings"""
        logger.info("Generating product mappings...")
        
        matched_mappings = []
        unmatched_products = []
        
        for local_product in self.local_products:
            local_id = local_product.get('id', '')
            local_name = local_product.get('name', '')
            
            if not local_id:
                continue
                
            match_result = self.find_best_match(local_product)
            
            if match_result:
                syrve_product, similarity = match_result
                mapping = {
                    'local_id': local_id,
                    'syrve_guid': syrve_product['id'],
                    'local_name': local_name,
                    'syrve_name': syrve_product['name'],
                    'similarity': similarity
                }
                matched_mappings.append(mapping)
                logger.info(f"Matched: {local_name} -> {syrve_product['name']} (similarity: {similarity:.2f})")
            else:
                unmatched_products.append({
                    'local_id': local_id,
                    'local_name': local_name
                })
                logger.warning(f"No match found for: {local_name}")
                
        return matched_mappings, unmatched_products
    
    def save_mapping_file(self, mappings: List[Dict], output_path: str):
        """Save mappings to CSV file"""
        try:
            logger.info(f"Saving mappings to {output_path}")
            
            with open(output_path, 'w', encoding='utf-8', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(['local_id', 'syrve_guid'])
                
                for mapping in mappings:
                    writer.writerow([mapping['local_id'], mapping['syrve_guid']])
                    
            logger.info(f"Successfully saved {len(mappings)} mappings")
            
        except Exception as e:
            logger.error(f"Error saving mapping file: {e}")
    
    def save_report(self, mappings: List[Dict], unmatched: List[Dict], report_path: str):
        """Save detailed mapping report"""
        try:
            logger.info(f"Saving detailed report to {report_path}")
            
            with open(report_path, 'w', encoding='utf-8') as file:
                file.write("AUTOMATIC PRODUCT MAPPING REPORT\n")
                file.write("=" * 50 + "\n\n")
                
                file.write(f"Total local products: {len(self.local_products)}\n")
                file.write(f"Total Syrve products: {len(self.syrve_products)}\n")
                file.write(f"Successfully matched: {len(mappings)}\n")
                file.write(f"Unmatched products: {len(unmatched)}\n")
                file.write(f"Match rate: {len(mappings) / len(self.local_products) * 100:.1f}%\n\n")
                
                file.write("MATCHED PRODUCTS:\n")
                file.write("-" * 30 + "\n")
                for mapping in mappings:
                    file.write(f"Local: {mapping['local_name']}\n")
                    file.write(f"Syrve: {mapping['syrve_name']}\n")
                    file.write(f"Similarity: {mapping['similarity']:.2f}\n")
                    file.write(f"Local ID: {mapping['local_id']}\n")
                    file.write(f"Syrve GUID: {mapping['syrve_guid']}\n")
                    file.write("-" * 30 + "\n")
                
                if unmatched:
                    file.write("\nUNMATCHED PRODUCTS:\n")
                    file.write("-" * 30 + "\n")
                    for product in unmatched:
                        file.write(f"Name: {product['local_name']}\n")
                        file.write(f"ID: {product['local_id']}\n")
                        file.write("-" * 30 + "\n")
                        
            logger.info("Report saved successfully")
            
        except Exception as e:
            logger.error(f"Error saving report: {e}")

async def main():
    """Main function to run the automatic product mapping"""
    matcher = ProductMatcher()
    
    # Paths
    base_dir = Path(__file__).parent.parent
    local_products_path = base_dir / "data" / "base_products.csv"
    mapping_output_path = base_dir / "data" / "syrve_mapping.csv"
    report_output_path = base_dir / "data" / "mapping_report.txt"
    
    # Load local products
    if not matcher.load_local_products(str(local_products_path)):
        logger.error("Failed to load local products")
        return
    
    # Fetch Syrve products
    if not await matcher.fetch_syrve_products():
        logger.error("Failed to fetch Syrve products")
        return
    
    # Generate mappings
    mappings, unmatched = matcher.generate_mappings()
    
    # Save results
    matcher.save_mapping_file(mappings, str(mapping_output_path))
    matcher.save_report(mappings, unmatched, str(report_output_path))
    
    # Summary
    total_products = len(matcher.local_products)
    matched_count = len(mappings)
    match_rate = (matched_count / total_products * 100) if total_products > 0 else 0
    
    print(f"\n{'='*50}")
    print("AUTOMATIC PRODUCT MAPPING COMPLETED")
    print(f"{'='*50}")
    print(f"Total products processed: {total_products}")
    print(f"Successfully matched: {matched_count}")
    print(f"Unmatched products: {len(unmatched)}")
    print(f"Match rate: {match_rate:.1f}%")
    print(f"\nMapping file updated: {mapping_output_path}")
    print(f"Detailed report saved: {report_output_path}")

if __name__ == "__main__":
    asyncio.run(main())