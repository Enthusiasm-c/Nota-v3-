from decimal import Decimal
import html  # Импорт для экранирования HTML-спецсимволов

# Fixed column widths for the mobile-friendly invoice table
W_IDX = 3
W_NAME = 14
W_QTY = 5
W_UNIT = 4
W_PRICE = 10
W_STATUS = 2
FMT_ROW = "{idx:<3} {name:<14} {qty:>5} {unit:<4} {price:>10} {status}"  # status теперь всегда виден
DIVIDER = "_______________________________"  # 31 символ


def format_idr(val):
    """Format number with narrow space and no currency for table."""
    try:
        val = Decimal(val)
        return f"{val:,.0f}".replace(",", "\u202f")
    except Exception:
        return "—"


def _row(idx, name, qty, unit, price, status, escape=False):
    # Формируем статус с эмодзи и текстом
    if status == "ok":
        status_str = "✔️"
    elif status == "unknown":
        status_str = "❌"
    elif status == "unit_mismatch":
        status_str = "⚠️ unit mismatch"
    else:
        status_str = status
    # Truncate name if too long
    if len(name) > W_NAME:
        name = name[: W_NAME - 1] + "…"
    # Экранирование HTML
    if escape:
        name = html.escape(name)
        unit = html.escape(str(unit))
        status_str = html.escape(status_str)
    # Format qty with narrow space
    try:
        qty_str = f"{int(qty):,}".replace(",", "\u202f")
    except Exception:
        qty_str = str(qty)
    # Format price
    price_str = format_idr(price) if price is not None else "—"
    return FMT_ROW.format(
        idx=str(idx),
        name=name,
        qty=qty_str,
        unit=str(unit),
        price=price_str,
        status=status_str,
    )


def build_table(match_results):
    status_map = {
        "ok": "✓",
        "unit_mismatch": "🚫",
        "unknown": "🚫",
        "ignored": "🚫",
        "error": "🚫"
    }
    table_rows = []
    for idx, item in enumerate(match_results, 1):
        status = item.get("status", "")
        status_str = status_map.get(status, "")
        price_val = item.get("price", "")
        price_str = "" if price_val is None else price_val
        row = FMT_ROW.format(
            idx=idx,
            name=item.get("name", ""),
            qty=item.get("qty", ""),
            unit=item.get("unit", ""),
            price=price_str,
            status=status_str
        )
        table_rows.append(row)
    header = "#   NAME                 QTY UNIT        TOTAL ⚑"
    divider = "─" * len(header)
    table = header + "\n" + divider + "\n"
    body = "\n".join(table_rows)
    table += body
    return f"<pre>{table}</pre>"



def paginate_rows(rows, page_size=15):
    """Split rows into pages of page_size."""
    return [rows[i : i + page_size] for i in range(0, len(rows), page_size)]


def build_report(parsed_data, match_results, escape=True, page=1, page_size=15):
    """
    Build a mobile-friendly invoice report with pagination.
    Returns (html_text, has_errors).
    """
    supplier = getattr(parsed_data, "supplier", None)
    if supplier is None and isinstance(parsed_data, dict):
        supplier = parsed_data.get("supplier", None)
    date = getattr(parsed_data, "date", None)
    if date is None and isinstance(parsed_data, dict):
        date = parsed_data.get("date", None)
    supplier_str = "Unknown supplier" if not supplier else html.escape(str(supplier))
    date_str = "—" if not date else html.escape(str(date))

    ok_total = 0
    mismatch_total = 0
    unknown_count = 0
    has_errors = False
    for idx, pos in enumerate(match_results, 1):
        line_total = pos.get("line_total", None)
        status = pos.get("status", "")
        if status == "ok":
            ok_total += float(line_total) if line_total else 0
        elif status == "unit_mismatch":
            mismatch_total += float(line_total) if line_total else 0
            has_errors = True
        elif status in ("unknown", "ignored", "error"):
            unknown_count += 1
            has_errors = True

    start = (page - 1) * page_size
    end = start + page_size
    rows_to_show = match_results[start:end]
    table = build_table(rows_to_show)
    total_pages = max(1, (len(match_results) + page_size - 1) // page_size)

    html = f"""
    <div style='background:#fff; color:#222; font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; border-radius:18px; box-shadow:0 2px 16px #0001; padding:18px 10px 10px 10px; max-width:410px; margin:auto;'>
        <div style='font-size:1.1em; font-weight:600; margin-bottom:2px;'>Supplier: <span style='font-weight:400'>{supplier_str}</span></div>
        <div style='font-size:1.1em; font-weight:600; margin-bottom:8px;'>Invoice date: <span style='font-weight:400'>{date_str}</span></div>
        {table}
        <div style='margin-top:10px; font-size:0.97em; color:#222;'>
            <b>✓</b> Correct: {len([r for r in match_results if r.get('status') == 'ok'])} &nbsp; 
            <b>🚫</b> Issues: {len([r for r in match_results if r.get('status') in ['unit_mismatch', 'unknown', 'ignored', 'error']])}
        </div>
        {f'<div style="margin-top:6px; font-size:0.95em; color:#888;">Page {page} / {total_pages}</div>' if total_pages > 1 else ''}
    </div>
    """
    return html.strip(), has_errors
