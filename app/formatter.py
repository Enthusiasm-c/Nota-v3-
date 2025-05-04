from decimal import Decimal, InvalidOperation
from typing import Any

# Ширины колонок для табличного отчёта
W_IDX = 3
W_NAME = 22
W_QTY = 6
W_UNIT = 6
W_PRICE = 10
W_TOTAL = 11
W_STATUS = 12


def escape_md(text: str, version: int = 2) -> str:
    # Escapes all special characters for MarkdownV2
    # https://core.telegram.org/bots/api#markdownv2-style
    if not isinstance(text, str):
        text = str(text)
    specials = r"_*[]()~`>#+-=|{}.!"
    for c in specials:
        text = text.replace(c, f"\\{c}")
    return text




def format_idr(val: Any) -> str:
    """Форматирует число в стиль '1 234 567 IDR' с узким пробелом"""
    try:
        if val is None:
            return "—"
        dec = Decimal(str(val))
        return (
            f"{dec:,.0f}".replace(",", "\u2009") + " IDR"
        )
    except (InvalidOperation, ValueError, TypeError):
        return "—"


def _row(
    idx: str | int,
    name: str,
    qty: str | int | float,
    unit: str,
    price: Any,
    total: Any,
    status: str | None,
) -> str:
    name = (name[: W_NAME - 1] + "…") if len(name) > W_NAME else name
    price_str = format_idr(price) if price not in (None, "") else "—"
    total_str = format_idr(total) if total not in (None, "") else "—"
    status_str = status if status else ""
    return (
        f"{str(idx).ljust(W_IDX)}"
        f"{name.ljust(W_NAME)}"
        f"{str(qty).rjust(W_QTY)} "
        f"{unit.ljust(W_UNIT)} "
        f"{price_str.rjust(W_PRICE)} "
        f"{total_str.rjust(W_TOTAL)} "
        f"{status_str}"
    )


# build_table удалён — используйте app/formatters/report.py


from typing import Any

# build_report и build_table удалены — используйте app/formatters/report.py
) -> str:
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
                "Unknown supplier"
                if not supplier
                else escape_md(str(supplier), version=2)
            )
            date_str = "—" if not date else escape_md(str(date), version=2)
        else:
            supplier_str = (
                "Unknown supplier" if not supplier else str(supplier)
            )
            date_str = "—" if not date else str(date)

        # Подсчитываем статистику по позициям
        ok_count = sum(1 for r in match_results if r.get("status") == "ok")
        unit_mismatch_count = sum(
            1 for r in match_results if r.get("status") == "unit_mismatch"
        )
        unknown_count = sum(
            1 for r in match_results if r.get("status") == "unknown"
        )
        need_check_count = unit_mismatch_count + unknown_count

        # Формируем заголовок
        report = (
            f"\U0001f4e6 *Supplier:* {supplier_str}\n"
            f"\U0001f4c6 *Invoice date:* {date_str}\n"
        )
        # Первый разделитель

        # Формируем строки таблицы
        rows = []
        ok_total: float = 0.0
        mismatch_total: float = 0.0
        for idx, pos in enumerate(match_results, 1):
            name = pos.get("name", "")
            qty = pos.get("qty", "")
            unit = pos.get("unit", "")
            price = pos.get("price", "")
            line_total = pos.get("line_total", "")
            status = pos.get("status", "")
            # Только допустимые статусы, иначе строка не добавляется
            if status not in ("ok", "unit_mismatch", "unknown"):
                continue
            if escape:
                name = escape_md(str(name), version=2)
                unit = escape_md(str(unit), version=2)
            if status == "ok":
                ok_total += float(line_total) if line_total else 0
                status_str = "✅ ok"
            elif status == "unit_mismatch":
                mismatch_total += float(line_total) if line_total else 0
                status_str = "⚖️ unit mismatch"
            elif status == "unknown":
                status_str = "❓ not found"
            rows.append(_row(idx, name, qty, unit, price, line_total, status_str))
        # Таблица внутри блока кода
        report += "```\n"
        report += _row("#", "NAME", "QTY", "UNIT", "PRICE", "TOTAL", "STATUS") + "\n"
        report += "────────────────────────────────────────\n"
        if rows:
            report += "\n".join(rows) + "\n"
        report += "```\n"
        # Divider после таблицы
        report += "────────────────────────────────────────\n"
        # После блока кода divider НЕ добавляем, сразу summary
        report += "░░ Сводка ░░\n"
        if ok_count > 0:
            report += f"✅ ok: {ok_count} ({format_idr(ok_total)})\n"
        if unit_mismatch_count > 0:
            report += (
                f"⚖ mismatch: {unit_mismatch_count} ({format_idr(mismatch_total)})\n"
            )
        if unknown_count > 0:
            report += f"❓ not-found: {unknown_count} (—)\n"
        # Divider после summary
        report += "────────────────────────────────────────\n"
        invoice_total: float = ok_total + mismatch_total
        # Итоговая строка
        summary_status = ""
        if ok_count > 0 and need_check_count == 0:
            summary_status = "ok"
        elif need_check_count > 0:
            summary_status = "need check"
        report += f"💰 Invoice total: *{format_idr(invoice_total)}*"
        if summary_status:
            report += f"  {summary_status}"
        return report.strip()

    except Exception as e:
        # Логируем ошибку и возвращаем минимальную безопасную информацию
        logger.error(f"Error building report: {e}")
        # Формируем минимальный отчет, который точно не вызовет ошибку форматирования
        basic_report = f"Found {len(match_results)} positions.\n"
        basic_report += f"Complete: {ok_count}, Need verification: {need_check_count}"
        return basic_report
