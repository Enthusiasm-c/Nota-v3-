import csv
from typing import List, Dict
from pathlib import Path

def load_suppliers(path: str = "data/suppliers.csv") -> List[Dict]:
    with open(path, encoding='utf-8') as f:
        return list(csv.DictReader(f))

from app.alias import read_aliases

def load_units() -> list:
    # Можно заменить на загрузку из файла, если потребуется
    return ["kg", "g", "l", "ml", "pcs", "pack"]

def load_products(products_path: str = "data/base_products.csv", aliases_path: str = "data/aliases.csv") -> List[Dict]:
    with open(products_path, encoding='utf-8') as f:
        products = list(csv.DictReader(f))
    id_to_product = {p["id"]: p for p in products}
    aliases = read_aliases(aliases_path)
    # Merge aliases as virtual products
    for alias, pid in aliases.items():
        if pid in id_to_product:
            prod_copy = id_to_product[pid].copy()
            prod_copy["alias"] = alias
            products.append(prod_copy)
    return products
