from html import escape  # Для экранирования только данных, не тегов
from decimal import Decimal

def format_idr(val):
    """Format number with narrow space and no currency for table."""
    try:
        val = Decimal(val)
        return f"{val:,.0f}".replace(",", "\u202f")
    except Exception:
        return "—"




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
        total_str = format_idr(total) if total not in (None, "") else "—"
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
