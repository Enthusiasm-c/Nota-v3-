import csv
from pathlib import Path
from typing import Dict, Optional

def read_aliases(path: str = "data/aliases.csv") -> Dict[str, str]:
    aliases = {}
    if not Path(path).exists():
        return aliases
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            alias = row.get("alias", "").strip().lower()
            pid = row.get("product_id", "").strip()
            if alias and pid:
                aliases[alias] = pid
    return aliases

def add_alias(alias: str, product_id: str, path: str = "data/aliases.csv") -> bool:
    alias = alias.strip().lower()
    product_id = product_id.strip()
    aliases = read_aliases(path)
    if alias in aliases and aliases[alias] == product_id:
        return False  # Already exists
    with open(path, "a", encoding="utf-8", newline='') as f:
        writer = csv.writer(f)
        if Path(path).stat().st_size == 0:
            writer.writerow(["alias", "product_id"])
        writer.writerow([alias, product_id])
    return True
