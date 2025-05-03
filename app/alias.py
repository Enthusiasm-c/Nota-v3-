import csv
import os
from pathlib import Path
from typing import Dict, Optional

def read_aliases(path: str = "data/aliases.csv") -> Dict[str, tuple[str, str]]:
    # print(f"DEBUG: read_aliases called with path={path}")
    aliases = {}
    if not Path(path).exists():
        # print(f"DEBUG: Aliases file '{path}' does not exist")
        return aliases
    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header
        for row in reader:
            # print(f"DEBUG: Read row from aliases: {row}")
            if len(row) >= 2:
                alias, pid = row[0], row[1]
                alias_l = alias.lower()
                aliases[alias_l] = (pid, alias)
    # print(f"DEBUG: Final aliases dict: {aliases}")
    return aliases

def add_alias(alias: str, product_id: str, path: str = "data/aliases.csv") -> bool:
    alias = alias.strip().lower()
    product_id = product_id.strip()
    aliases = read_aliases(path)
    if alias in aliases and aliases[alias][0] == product_id:
        return False  # Already exists
    write_header = not Path(path).exists() or Path(path).stat().st_size == 0
    with open(path, "a", encoding="utf-8", newline='') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["alias", "product_id"])
        writer.writerow([alias, product_id])
        # print(f"DEBUG: Added alias '{alias}' for product_id '{product_id}' to '{path}'")
        f.flush()
        os.fsync(f.fileno())
    if Path(path).exists():
        with open(path, encoding="utf-8") as f_check:
            pass
    else:
        pass
    return True
