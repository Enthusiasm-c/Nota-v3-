from app.data_loader import load_products, load_units

from typing import Iterable, Optional
from app.models import Product


def build_prompt(products: Optional[Iterable[Product]] = None) -> str:
    """Формирует text-prefix для Vision-запроса."""
    if products is None:
        products = load_products()
    aliases = [p.alias for p in products]
    units = load_units()

    lines = [
        "CONTEXT:",
        "Allowed products:",
        *[f"- {name}" for name in sorted(set(aliases))],
        "",
        "Allowed units:",
        *[f"- {u}" for u in units],
        "",
        "Return JSON list: ",
        "[{line:int, name:str, qty:float, unit:str, price:int}]",
    ]
    return "\n".join(lines)
