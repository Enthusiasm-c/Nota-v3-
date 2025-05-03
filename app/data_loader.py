import csv
from typing import List, Dict
from pathlib import Path
from functools import lru_cache
from app.models import Product

def load_suppliers(path: str = "data/suppliers.csv") -> List[Dict]:
    with open(path, encoding='utf-8') as f:
        return list(csv.DictReader(f))

from app.alias import read_aliases

def load_units() -> list:
    # Можно заменить на загрузку из файла, если потребуется
    return ["kg", "g", "l", "ml", "pcs", "pack"]

@lru_cache(maxsize=1)
def load_products(products_path: str = "data/base_products.csv", aliases_path: str = "data/aliases.csv") -> list[Product]:
    with open(products_path, encoding='utf-8') as f:
        products = list(csv.DictReader(f))
    id_to_product = {p["id"]: p for p in products}
    aliases = read_aliases(aliases_path)
    # Merge aliases as virtual products
    product_objs = []
    for p in products:
        product_objs.append(Product(
            id=p.get("id", ""),
            code=p.get("code", ""),
            name=p.get("name", ""),
            alias=p.get("alias", p.get("name", "")),
            unit=p.get("unit", ""),
            price_hint=float(p["price_hint"]) if p.get("price_hint") else None
        ))
    for alias, pid in aliases.items():
        if pid in id_to_product:
            prod = id_to_product[pid]
            product_objs.append(Product(
                id=prod.get("id", ""),
                code=prod.get("code", ""),
                name=prod.get("name", ""),
                alias=alias,
                unit=prod.get("unit", ""),
                price_hint=float(prod["price_hint"]) if prod.get("price_hint") else None
            ))
    return product_objs
