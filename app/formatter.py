from decimal import Decimal

# Ширины колонок для табличного отчёта
W_IDX = 3
W_NAME = 22
W_QTY = 6
W_UNIT = 6
W_PRICE = 10
W_TOTAL = 11
W_STATUS = 12

def escape_md(text, version=2):
    # Escapes all special characters for MarkdownV2
    # https://core.telegram.org/bots/api#markdownv2-style
    if not isinstance(text, str):
        text = str(text)
    specials = r"_*[]()~`>#+-=|{}.!"
    for c in specials:
        text = text.replace(c, f"\\{c}")
    return text

def format_idr(val):
    """Форматирует число в стиль '1 234 567 IDR' с узким пробелом"""
    try:
        val = Decimal(val)
        return f"{val:,.0f}".replace(",", "\u2009") + " IDR"
    except Exception:
        return "—"

def _row(idx, name, qty, unit, price, total, status):
    name = (name[:W_NAME-1] + "…") if len(name) > W_NAME else name
    # Корректно форматируем price и total
    try:
        price_val = float(price)
        price_str = f"{price_val:,.0f}"
    except (TypeError, ValueError):
        price_str = "—"
    try:
        total_val = float(total)
        total_str = f"{total_val:,.0f}"
    except (TypeError, ValueError):
        total_str = "—"
    return (
        f"{str(idx).ljust(W_IDX)}"
        f"{name.ljust(W_NAME)}"
        f"{str(qty).rjust(W_QTY)} "
        f"{unit.ljust(W_UNIT)} "
        f"{price_str.rjust(W_PRICE)} "
        f"{total_str.rjust(W_TOTAL)} "
        f"{status}"
    )

def build_table(rows: list[str]) -> str:
    header = _row("#", "NAME", "QTY", "UNIT", "PRICE", "TOTAL", "STATUS")
    divider = "─" * len(header)
    body = "\n".join(rows)
    return f"```\n{header}\n{divider}\n{body}\n```"

def build_report(parsed_data, match_results: list, escape=True) -> str:
    """
    Формирует отчет по инвойсу в формате MarkdownV2.
    Args:
        parsed_data: Данные инвойса (объект ParsedData или словарь)
        match_results: Результаты сопоставления позиций
        escape: Нужно ли экранировать специальные символы Markdown
        
    Returns:
        str: Форматированный отчет для отправки в Telegram
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        # Support both dict and ParsedData object
        supplier = getattr(parsed_data, "supplier", None)
        if supplier is None and isinstance(parsed_data, dict):
            supplier = parsed_data.get("supplier", None)
        date = getattr(parsed_data, "date", None)
        if date is None and isinstance(parsed_data, dict):
            date = parsed_data.get("date", None)
            
        # В зависимости от параметра escape, экранируем или нет
        if escape:
            supplier_str = (
                "Unknown supplier" if not supplier else escape_md(str(supplier), version=2)
            )
            date_str = (
                "—" if not date else escape_md(str(date), version=2)
            )
        else:
            supplier_str = (
                "Unknown supplier" if not supplier else str(supplier)
            )
            date_str = (
                "—" if not date else str(date)
            )
            
        # Подсчитываем статистику по позициям
        ok_count = sum(
            1 for r in match_results if r.get("status") == "ok"
        )
        unit_mismatch_count = sum(
            1 for r in match_results if r.get("status") == "unit_mismatch"
        )
        unknown_count = sum(
            1 for r in match_results if r.get("status") == "unknown"
        )
        need_check_count = unit_mismatch_count + unknown_count
        
        # Формируем заголовок
        report = (
        f"\U0001F4E6 *Supplier:* {supplier_str}\n"
        f"\U0001F4C6 *Invoice date:* {date_str}\n"
    )
        report += "────────────────────────────────────────\n"
        
        # Создаем строки для таблицы позиций
        rows = []
        ok_total = 0
        mismatch_total = 0
        unknown_count = 0
        for idx, pos in enumerate(match_results, 1):
            name = pos.get("name", "")
            qty = pos.get("qty", "")
            unit = pos.get("unit", "")
            price = pos.get("price", "")
            line_total = pos.get("line_total", "")
            status = pos.get("status", "")
            status_str = ""
            if status == "ok":
                ok_total += float(line_total) if line_total else 0
                status_str = "✅ ok"
            elif status == "unit_mismatch":
                mismatch_total += (
                    float(line_total) if line_total else 0
                )
                status_str = "⚖️ unit mismatch"
            elif status == "unknown":
                unknown_count += 1
                status_str = "❓ not found"
            else:
                status_str = (
                    escape_md(str(status), version=2) if escape else str(status)
                )
            rows.append(_row(idx, name, qty, unit, price, line_total, status_str))
        report += build_table(rows) + "\n"
        report += "────────────────────────────────────────\n"
        # --- Блок «Итоги» ---
        report += (
            "░░ Сводка ░░\n"
        )
        report += (
            f"✅ ok: {len([r for r in match_results if r.get('status') == 'ok'])} "
            f"({format_idr(ok_total)})\n"
        )
        report += (
            f"⚖ mismatch: {len([r for r in match_results if r.get('status') == 'unit_mismatch'])} "
            f"({format_idr(mismatch_total)})\n"
        )
        report += (
            f"❓ not-found: {unknown_count} (—)\n"
        )
        report += (
            "──────────────────────\n"
        )
        invoice_total = (
            ok_total + mismatch_total
        )
        report += (
            f"💰 Invoice total: *{format_idr(invoice_total)}*\n"
        )
        return report.strip()

        
    except Exception as e:
        # Логируем ошибку и возвращаем минимальную безопасную информацию
        logger.error(f"Error building report: {e}")
        
        # Формируем минимальный отчет, который точно не вызовет ошибку форматирования
        basic_report = f"Found {len(match_results)} positions.\n"
        basic_report += (
            f"Complete: {ok_count}, Need verification: {need_check_count}"
        )
        return basic_report
