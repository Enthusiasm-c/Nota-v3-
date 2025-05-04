from decimal import Decimal

# Fixed column widths for the mobile-friendly invoice table
W_IDX = 3
W_NAME = 19
W_QTY = 8
W_UNIT = 4
W_TOTAL = 13
W_STATUS = 2
FMT_ROW = "{idx:<3} {name:<19} {qty:>8} {unit:<4} {total:>13} {status}"


def format_idr(val):
    """Format number with narrow space and no currency for table."""
    try:
        val = Decimal(val)
        return f"{val:,.0f}".replace(",", "\u202f")
    except Exception:
        return "—"


def _row(idx, name, qty, unit, total, status):
    # Truncate name if too long
    if len(name) > W_NAME:
        name = name[: W_NAME - 1] + "…"
    # Format qty with narrow space
    try:
        qty_str = f"{int(qty):,}".replace(",", "\u202f")
    except Exception:
        qty_str = str(qty)
    # Format total
    total_str = format_idr(total) if total is not None else "—"
    # Status: ⚠️ для ошибок, пусто для ok
    status_emoji = ""
    if status in ("unit_mismatch", "unknown"):
        status_emoji = "⚠️"
    elif status == "ok":
        status_emoji = ""
    return FMT_ROW.format(
        idx=str(idx),
        name=name,
        qty=qty_str,
        unit=str(unit),
        total=total_str,
        status=status_emoji,
    )


def build_table(rows):
    # Удаляем divider-строки из rows, если они есть
    rows = [r for r in rows if set(r.strip()) != {'─'}]
    header = FMT_ROW.format(
        idx="#",
        name="NAME",
        qty="QTY",
        unit="UNIT",
        total="TOTAL",
        status="",
    )
    body = "\n".join(rows)
    table = f"{header}\n{body}"
    # Markdown V2: тройные обратные кавычки, без языка
    return f"\n```\n{table}\n```\n"


def paginate_rows(rows, page_size=15):
    """Split rows into pages of page_size."""
    return [rows[i : i + page_size] for i in range(0, len(rows), page_size)]


def build_report(parsed_data, match_results, escape=True, page=1, page_size=15):
    """
    Build a mobile-friendly invoice report with pagination.
    Возвращает (text, has_errors)
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
    has_errors = False
    for idx, pos in enumerate(match_results, 1):
        name = pos.get("name", "")
        qty = pos.get("qty", "")
        unit = pos.get("unit", "")
        price = pos.get("price", None)
        line_total = pos.get("line_total", None)
        status = pos.get("status", "")
        emoji = ""
        if status == "ok":
            emoji = ""
            ok_total += float(line_total) if line_total else 0
        elif status == "unit_mismatch":
            emoji = "⚠️"
            mismatch_total += float(line_total) if line_total else 0
            has_errors = True
        elif status == "unknown":
            emoji = "⚠️"
            unknown_count += 1
            has_errors = True
        table_rows.append(_row(idx, name, qty, unit, line_total, status))

    # Pagination
    pages = paginate_rows(table_rows, page_size)
    total_pages = len(pages)
    page = max(1, min(page, total_pages))
    current_rows = pages[page - 1] if pages else []

    # Build table for current page
    table = build_table(current_rows)

    # Header and summary
    report = (
        f"\U0001f4e6 *Supplier:* {supplier_str}\n"
        f"\U0001f4c6 *Invoice date:* {date_str}\n"
        "────────────────────────────────────────\n"
    )
    if has_errors:
        report += "⚠️ Обнаружены ошибки — исправьте их перед отправкой!\n"
    report += table

    report += "░░ Сводка ░░\n"
    report += (
        f"ok: {len([r for r in match_results if r.get('status') == 'ok'])} "
        f"({format_idr(ok_total)})\n"
    )
    report += (
        f"ошибки: {len([r for r in match_results if r.get('status') in ['unit_mismatch', 'unknown']])} "
        f"({format_idr(mismatch_total)})\n"
    )
    report += f"не найдено: {unknown_count} (—)\n"
    report += "──────────────────────\n"
    invoice_total = ok_total + mismatch_total
    report += f"💰 Invoice total: *{format_idr(invoice_total)} IDR*\n"
    report += f"Страница {page} из {total_pages}\n" if total_pages > 1 else ""
    return report.strip(), has_errors
