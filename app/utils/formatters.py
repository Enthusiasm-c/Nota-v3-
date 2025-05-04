def format_idr(val):
    """Format number with narrow space and 'IDR' suffix (e.g. 12342567 IDR)."""
    try:
        val = float(val)
        return f"{val:,.0f}".replace(",", "\u202f") + " IDR"
    except Exception:
        return "—"

def fmt_num(val):
    """Format number with narrow space, no currency."""
    try:
        val = float(val)
        return f"{val:,.0f}".replace(",", "\u202f")
    except Exception:
        return "—"
