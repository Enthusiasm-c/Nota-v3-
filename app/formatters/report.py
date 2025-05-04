from decimal import Decimal
from html import escape  # Для экранирования только данных, не тегов
from app.utils.formatters import fmt_num

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
        name = item.get("name", "")
        if len(name) > 14:
            name = name[:14] + "…"
        price_val = item.get("price", "")
        price_str = "" if price_val is None else price_val
        row = FMT_ROW.format(
            idx=idx,
            name=name,
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
    return table



def paginate_rows(rows, page_size=15):
    """Split rows into pages of page_size."""
    return [rows[i : i + page_size] for i in range(0, len(rows), page_size)]


def build_header(supplier, date):
    return (
        f"<b>Supplier:</b> {escape(str(supplier))}<br>"
        f"<b>Invoice date:</b> {escape(str(date))}<br><br>"
    )

def build_table(rows):
    status_map = {"ok": "✓", "unit_mismatch": "🚫", "unknown": "🚫", "ignored": "🚫", "error": "🚫"}
    header = "#  NAME                 QTY UNIT        TOTAL  ⚑"
    divider = "─" * len(header)
    table_rows = [header, divider]
    for idx, item in enumerate(rows, 1):
        name = item.get("name", "")
        if len(name) > 19:
            name = name[:18] + "…"
        name = escape(name)
        qty = item.get("qty", "")
        unit = escape(item.get("unit", ""))
        total = item.get("line_total", "")
        total_str = fmt_num(total) if total not in (None, "") else "—"
        status = item.get("status", "")
        status_str = status_map.get(status, "")
        row = f"{idx:<2} {name:<19} {qty:>6} {unit:<4} {total_str:>12} {status_str}"
        table_rows.append(row)
    return "\n".join(table_rows)

def build_summary(ok_count, issues_count, invoice_total):
    return (
        f"<b>✓ Correct:</b> {ok_count}&nbsp;&nbsp;<b>🚫 Issues:</b> {issues_count}<br>"
        f"<b>💰 Invoice total:</b> {format_idr(invoice_total)}"
    )

def build_report(parsed_data, match_results, escape=True, page=1, page_size=15):
    supplier = getattr(parsed_data, "supplier", None)
    if supplier is None and isinstance(parsed_data, dict):
        supplier = parsed_data.get("supplier", None)
    date = getattr(parsed_data, "date", None)
    if date is None and isinstance(parsed_data, dict):
        date = parsed_data.get("date", None)
    supplier_str = "Unknown supplier" if not supplier else supplier
    date_str = "—" if not date else date

    # Pagination
    start = (page - 1) * page_size
    end = start + page_size
    rows_to_show = match_results[start:end]

    # Build table and summary
    ok_count = 0
    issues_count = 0
    invoice_total = 0
    for item in rows_to_show:
        status = item.get("status", "")
        if status == "ok":
            ok_count += 1
        elif status in ("unit_mismatch", "unknown", "ignored", "error"):
            issues_count += 1
        try:
            total = float(item.get("line_total", 0) or 0)
            invoice_total += total
        except Exception:
            pass
    header_html = build_header(supplier_str, date_str)
    table = build_table(rows_to_show)
    summary_html = build_summary(ok_count, issues_count, invoice_total)
    html_report = (
        f"{header_html}"
        f"<pre>{table}</pre>"
        f"{summary_html}"
    )
    return html_report.strip(), issues_count > 0
