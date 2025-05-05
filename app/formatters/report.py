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
        f"<b>Supplier:</b> {html_escape(str(supplier))}<br>"
        f"<b>Invoice date:</b> {html_escape(str(date))}\n\n"
    )

def build_table(rows):
    """
    Формирует текстовую таблицу с позициями инвойса.
    Текст в таблице безопасно экранируется для HTML.
    """
    from html import escape as html_escape
    status_map = {"ok": "✓", "unit_mismatch": "🚫", "unknown": "🚫", "ignored": "🚫", "error": "🚫"}
    header = "#  NAME                 QTY  UNIT       TOTAL        ⚑"
    divider = "─" * len(header)
    table_rows = [header, divider]
    for idx, item in enumerate(rows, 1):
        name = item.get("name", "")
        # Truncate to 18 chars + ellipsis for 19 total (to match 'olive oil orille 5…')
        if len(name) > 18:
            name = name[:18] + "…"
        name = html_escape(name)
        qty = item.get("qty", "")
        unit = html_escape(item.get("unit", ""))
        total = item.get("line_total", "")
        total_str = format_idr(total) if total not in (None, "") else "—"
        status = item.get("status", "")
        status_str = status_map.get(status, "")
        row = f"{idx:<2} {name:<19} {qty:>4} {unit:<6} {total_str:>10} {status_str}"
        table_rows.append(row)
    return "\n".join(table_rows)


def build_summary(ok_count, issues_count, invoice_total):
    """
    Формирует HTML-итоги по инвойсу с количеством успешных и проблемных позиций
    и общей суммой.
    
    Важно: Telegram поддерживает только ограниченное подмножество HTML-тегов.
    Вместо <br> используем символ новой строки \n, вместо &nbsp; используем обычный пробел.
    """
    return (
        f"<b>✓ Correct:</b> {ok_count}  <b>🚫 Issues:</b> {issues_count}\n"
        f"<b>💰 Invoice total:</b> {format_idr(invoice_total)}"
    )



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
    for item in match_results:  # Считаем для всех позиций, а не только для показываемых
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
    
    # Собираем отчет
    # Используем HTML-форматирование для Telegram, который поддерживает тег <pre>
    html_report = (
        f"{header_html}"
        f"<pre>{table}</pre>\n"
        f"{summary_html}"
    )
    
    return html_report.strip(), issues_count > 0