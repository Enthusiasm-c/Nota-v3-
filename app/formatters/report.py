from decimal import Decimal

# Fixed column widths for the mobile-friendly invoice table
W_IDX = 3
W_NAME = 19
W_QTY = 8
W_UNIT = 4
W_PRICE = 13
W_STATUS = 2
FMT_ROW = "{idx:<3} {name:<19} {qty:>8} {unit:<4} {price:>13} {status}"
DIVIDER = "────────────────────"  # 20 символов


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
    # Экранирование
    if escape:
        from app.formatter import escape_md
        name = escape_md(name)
        unit = escape_md(str(unit))
        status_str = escape_md(status_str)
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


def build_table(rows):
    # Удаляем divider-строки из rows, если они есть
    rows = [r for r in rows if set(r.strip()) != {'─'}]
    # Заголовок всегда без экранирования!
    header = f"#   NAME{' ' * (W_NAME - 4)}QTY UNIT{' ' * (W_UNIT - 4)}PRICE{' ' * (W_PRICE - 5)}\n"
    table = header
    table += "-" * (W_IDX + W_NAME + W_QTY + W_UNIT + W_PRICE + W_STATUS + 6) + "\n"
    body = "\n".join(rows)
    table += body
    # Markdown V2: тройные обратные кавычки, без языка
    return f"```\n{table}\n```\n"


def paginate_rows(rows, page_size=15):
    """Split rows into pages of page_size."""
    return [rows[i : i + page_size] for i in range(0, len(rows), page_size)]


def build_report(parsed_data, match_results, escape=True, page=1, page_size=15):
    """
    Build a mobile-friendly invoice report with pagination.
    Возвращает (text, has_errors).
    Если escape=True, экранирует спецсимволы MarkdownV2 во всех полях.
    """
    if escape:
        from app.formatter import escape_md
    supplier = getattr(parsed_data, "supplier", None)
    if supplier is None and isinstance(parsed_data, dict):
        supplier = parsed_data.get("supplier", None)
    date = getattr(parsed_data, "date", None)
    if date is None and isinstance(parsed_data, dict):
        date = parsed_data.get("date", None)
    supplier_str = "Unknown supplier" if not supplier else str(supplier)
    date_str = "—" if not date else str(date)
    if escape:
        supplier_str = escape_md(supplier_str)
        date_str = escape_md(date_str)
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
        if status == "ok":
            ok_total += float(line_total) if line_total else 0
        elif status == "unit_mismatch":
            mismatch_total += float(line_total) if line_total else 0
            has_errors = True
        elif status == "unknown":
            unknown_count += 1
            has_errors = True
        table_rows.append(_row(idx, name, qty, unit, price, status, escape=escape))
    # Pagination
    pages = paginate_rows(table_rows, page_size)
    total_pages = len(pages)
    page = max(1, min(page, total_pages))
    current_rows = pages[page - 1] if pages else []
    # Build table for current page
    table = build_table(current_rows)

    # Header and summary
    report = (
        f"*Supplier:* {supplier_str}\n"
        f"*Invoice date:* {date_str}\n"
        f"{DIVIDER}\n"
    )

    report += table
    report += f"{DIVIDER}\n"
    if total_pages > 1:
        report += f"Страница {page} из {total_pages}\n"
    ok_count = len([r for r in match_results if r.get('status') == 'ok'])
    errors_count = len([r for r in match_results if r.get('status') in ['unit_mismatch', 'unknown']])
    report += f"Было успешно определено {ok_count} позиций\n"
    report += f"Позиции, требующие подтверждения: {errors_count} шт.\n"
    report += f"{DIVIDER}\n"
    return report.strip(), has_errors
