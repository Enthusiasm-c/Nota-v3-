from app.data_loader import load_products, load_units

def build_prompt() -> str:
    """Формирует text-prefix для Vision-запроса."""
    products = [p.alias for p in load_products()]
    units = load_units()

    lines = [
        "CONTEXT:",
        "Allowed products:",
        *[f"- {name}" for name in sorted(set(products))],
        "",
        "Allowed units:",
        *[f"- {u}" for u in units],
        "",
        "Return JSON list: ",
        "[{line:int, name:str, qty:float, unit:str, price:int}]"
    ]
    return "\n".join(lines)
