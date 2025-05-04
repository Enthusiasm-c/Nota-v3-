from decimal import Decimal

# Fixed column widths for the mobile-friendly invoice table
W_IDX = 3
W_NAME = 20
W_QTY = 8
W_UNIT = 4
W_PRICE = 11
W_TOTAL = 12
W_STATUS = 2
FMT_ROW = "{idx:<3} {name:<20} {qty:>8} {unit:<4} {price:>11} {total:>12} {status:>2}"


def format_idr(val):
    """Format number with narrow space and no currency for table."""
    try:
        val = Decimal(val)
        return f"{val:,.0f}".replace(",", "\u202F")
    except Exception:
        return "—"


def _row(idx, name, qty, unit, price, total, status):
    # Truncate name if too long
    if len(name) > W_NAME:
        name = name[:W_NAME-1] + "…"
    # Format numbers and handle None
    price_str = format_idr(price) if price is not None else "—"
    total_str = format_idr(total) if total is not None else "—"
    # Status: only emoji
    status_emoji = status if status in ("✅", "❓", "⚖️") else ""
    return FMT_ROW.format(
        idx=str(idx),
        name=name,
        qty=str(qty),
        unit=str(unit),
        price=price_str,
        total=total_str,
        status=status_emoji,
    )


def build_table(rows):
    header = FMT_ROW.format(
        idx="#", name="NAME", qty="QTY", unit="UNIT",
        price="PRICE", total="TOTAL", status=""
    )
    divider = "─" * len(header)
    body = "\n".join(rows)
    table = f"{header}\n{divider}\n{body}"
    return f"\n```\n{table}\n```\n"


def paginate_rows(rows, page_size=15):
    """Split rows into pages of page_size."""
    return [rows[i:i + page_size] for i in range(0, len(rows), page_size)]


def build_report(parsed_data, match_results, escape=True, page=1, page_size=15):
    """
    Build a mobile-friendly invoice report with pagination.
    """
    supplier = getattr(parsed_data, "supplier", None)
    if supplier is None and isinstance(parsed_data, dict):
        supplier = parsed_data.get("supplier", None)
    date = getattr(parsed_data, "date", None)
    if date is None and isinstance(parsed_data, dict):
        date = parsed_data.get("date", None)
    supplier_str = "Unknown supplier" if not supplier else str(supplier)
    date_str = "—" if not date else str(date)

    # Prepare table rows
    table_rows = []
    ok_total = 0
    mismatch_total = 0
    unknown_count = 0
    for idx, pos in enumerate(match_results, 1):
        name = pos.get("name", "")
        qty = pos.get("qty", "")
        unit = pos.get("unit", "")
        price = pos.get("price", None)
        line_total = pos.get("line_total", None)
        status = pos.get("status", "")
        emoji = ""
        if status == "ok":
            emoji = "✅"
            ok_total += float(line_total) if line_total else 0
        elif status == "unit_mismatch":
            emoji = "⚖️"
            mismatch_total += float(line_total) if line_total else 0
        elif status == "unknown":
            emoji = "❓"
            unknown_count += 1
        table_rows.append(_row(idx, name, qty, unit, price, line_total, emoji))

    # Pagination
    pages = paginate_rows(table_rows, page_size)
    total_pages = len(pages)
    page = max(1, min(page, total_pages))
    current_rows = pages[page-1] if pages else []

    # Build table for current page
    table = build_table(current_rows)

    # Header and summary
    report = (
        f"\U0001F4E6 *Supplier:* {supplier_str}\n"
        f"\U0001F4C6 *Invoice date:* {date_str}\n"
        "────────────────────────────────────────\n"
    )
    report += table
    report += "────────────────────────────────────────\n"
    report += "░░ Сводка ░░\n"
    report += (
        f"✅ ok: {len([r for r in match_results if r.get('status') == 'ok'])} "
        f"({format_idr(ok_total)})\n"
    )
    report += (
        f"⚖ mismatch: {len([r for r in match_results if r.get('status') == 'unit_mismatch'])} "
        f"({format_idr(mismatch_total)})\n"
    )
    report += f"❓ not-found: {unknown_count} (—)\n"
    report += "──────────────────────\n"
    invoice_total = ok_total + mismatch_total
    report += f"💰 Invoice total: *{format_idr(invoice_total)}*\n"
    report += f"Страница {page} из {total_pages}\n" if total_pages > 1 else ""
    return report.strip()
