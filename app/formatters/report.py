from html import escape  # Для экранирования только данных, не тегов
import logging
logging.getLogger("nota.report").debug("escape func = %s", escape)
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
    """
    Формирует HTML-заголовок отчета с информацией о поставщике и дате инвойса.
    Использует escape для безопасного включения данных в HTML.
    
    Важно: Telegram поддерживает только ограниченное подмножество HTML-тегов.
    Вместо <br> используем символ новой строки \n.
    """
    # Явно импортируем escape для надежности
    from html import escape as html_escape
    return (
        f"<b>Supplier:</b> {html_escape(str(supplier))}\n"
        f"<b>Invoice date:</b> {html_escape(str(date))}\n\n"
    )

def build_table(rows):
    """
    Формирует текстовую таблицу с позициями инвойса.
    Столбцы QTY, UNIT, PRICE выровнены по левому краю, TOTAL заменён на PRICE.
    """
    from html import escape as html_escape

    status_map = {"ok": "✓", "unit_mismatch": "🚫", "unknown": "🚫", "ignored": "🚫", "error": "🚫"}
    def pad(text, width):
        s = str(text)
        return s[:width].ljust(width)

    header = f"#  {pad('NAME',14)}{pad('QTY',5)}{pad('UNIT',5)}{pad('PRICE',6)}! "
    divider = '-' * len(header)
    table_rows = [header, divider]

    for idx, item in enumerate(rows, 1):
        name = item.get("name", "")
        if len(name) > 13:
            name = name[:12] + "…"
        name = html_escape(name)
        qty = item.get("qty", None)
        unit = html_escape(str(item.get("unit", "")))
        price = item.get("unit_price", None)
        total = item.get("total", None)
        status = item.get("status", "")
        # Попытка вычислить unit_price, если есть total и qty, но нет unit_price
        computed_price = None
        if (price in (None, "", "—")) and (total not in (None, "", "—")) and (qty not in (None, "", "—")):
            try:
                computed_price = float(total) / float(qty)
                price_str = format_idr(computed_price)
            except Exception:
                price_str = "—"
        else:
            price_str = format_idr(price) if price not in (None, "", "—") else "—"
        # Форматирование QTY: если целое — без .0, иначе с дробью
        if qty in (None, ""):
            qty_str = "—"
        else:
            try:
                qty_f = float(qty)
                if qty_f.is_integer():
                    qty_str = str(int(qty_f))
                else:
                    qty_str = str(qty)
            except Exception:
                qty_str = str(qty)
        # Столбец с флажком для нераспознанных позиций
        flag = "🚩" if status != "ok" else ""
        row = f"{str(idx):<2} {pad(name,14)}{pad(qty_str,5)}{pad(unit,5)}{pad(price_str,6)}{pad(flag,2)}"
        table_rows.append(row)

    return "\n".join(table_rows)


def build_summary(ok_count, issues_count, invoice_total, show_total=True, has_unparsed=False):
    """
    Формирует HTML-итоги по инвойсу с количеством успешных и проблемных позиций
    и общей суммой, если она доступна.
    """
    summary = f"<b>✓ Correct:</b> {ok_count}  <b>🚫 Issues:</b> {issues_count}\n"
    if show_total and not has_unparsed:
        summary += f"<b>💰 Invoice total:</b> {format_idr(invoice_total)}"
    elif has_unparsed:
        summary += "❗ Итоговая сумма не рассчитана: есть нераспознанные цены или количества."
    return summary

def build_report(parsed_data, match_results, escape_html=True, page=1, page_size=15):
    """
    Формирует HTML-отчет по инвойсу с пагинацией.
    
    Args:
        parsed_data: Распознанные данные инвойса (объект или словарь)
        match_results: Результаты сопоставления позиций с базой
        escape_html: Флаг экранирования HTML (True по умолчанию)
        page: Номер страницы для отображения
        page_size: Размер страницы (количество позиций)
        
    Returns:
        tuple: (HTML-отчет, флаг наличия ошибок)
    
    Важно: Telegram поддерживает только ограниченное подмножество HTML-тегов:
    <b>, <i>, <u>, <s>, <strike>, <del>, <a>, <code>, <pre>
    """
    # Извлекаем основную информацию из разных типов данных
    supplier = getattr(parsed_data, "supplier", None)
    if supplier is None and isinstance(parsed_data, dict):
        supplier = parsed_data.get("supplier", None)
    date = getattr(parsed_data, "date", None)
    if date is None and isinstance(parsed_data, dict):
        date = parsed_data.get("date", None)
    supplier_str = "Unknown supplier" if not supplier else supplier
    date_str = "—" if not date else date

    # Проверяем наличие потенциально опасных символов
    # Используем функцию escape из модуля html, а не параметр escape_html
    from html import escape as html_escape
    if supplier_str and isinstance(supplier_str, str):
        supplier_str = html_escape(supplier_str)
    if date_str and isinstance(date_str, str):
        date_str = html_escape(date_str)

    # Pagination
    start = (page - 1) * page_size
    end = start + page_size
    rows_to_show = match_results[start:end]

    # Build table and summary
    ok_count = 0
    issues_count = 0
    invoice_total = 0
    has_unparsed = False
    for item in match_results:
        status = item.get("status", "")
        if status == "ok":
            ok_count += 1
        elif status in ("unit_mismatch", "unknown", "ignored", "error"):
            issues_count += 1
        # Проверяем наличие нераспознанных цен или количеств
        qty = item.get("qty", None)
        price = item.get("unit_price", None)
        if qty in (None, "", "—") or price in (None, "", "—"):
            has_unparsed = True
        try:
            # Для подсчёта суммы используем только распознанные значения
            if not has_unparsed:
                invoice_total += float(qty) * float(price)
        except Exception:
            has_unparsed = True
    header_html = build_header(supplier_str, date_str)
    table = build_table(rows_to_show)
    summary_html = build_summary(ok_count, issues_count, invoice_total, show_total=not has_unparsed, has_unparsed=has_unparsed)
    html_report = (
        f"{header_html}"
        f"<pre>{table}</pre>\n"
        f"{summary_html}"
    )
    return html_report.strip(), issues_count > 0