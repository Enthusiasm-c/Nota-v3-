import csv
from typing import List, Dict

def load_suppliers(path: str) -> List[Dict]:
    with open(path, encoding='utf-8') as f:
        return list(csv.DictReader(f))

def load_products(path: str) -> List[Dict]:
    with open(path, encoding='utf-8') as f:
        return list(csv.DictReader(f))
