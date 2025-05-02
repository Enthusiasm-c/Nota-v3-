import csv
from typing import List, Dict
from pathlib import Path

def load_suppliers(path: str = "data/suppliers.csv") -> List[Dict]:
    with open(path, encoding='utf-8') as f:
        return list(csv.DictReader(f))

def load_products(products_path: str = "data/base_products.csv", aliases_path: str = "data/aliases.csv") -> List[Dict]:
    products = []
    with open(products_path, encoding='utf-8') as f:
        products = list(csv.DictReader(f))
    # Merge aliases
    aliases = []
    if Path(aliases_path).exists():
        with open(aliases_path, encoding='utf-8') as f:
            aliases = list(csv.DictReader(f))
    id_to_product = {p["id"]: p for p in products}
    for alias_row in aliases:
        alias = alias_row.get("alias")
        product_id = alias_row.get("product_id")
        if alias and product_id and product_id in id_to_product:
            orig = id_to_product[product_id]
            # Copy, but set alias as name
            prod_copy = orig.copy()
            prod_copy["alias"] = alias
            products.append(prod_copy)
    return products
