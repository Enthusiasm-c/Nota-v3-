from html import escape  # For escaping data only, not HTML tags
import logging
logging.getLogger("nota.report").debug("escape func = %s", escape)
from decimal import Decimal
from app.utils.formatters import format_price, format_quantity

def format_idr(val):
    """Format number with narrow space and no currency for table."""
    try:
        # Используем унифицированную функцию из общего модуля
        return format_price(val, currency="", decimal_places=0)
    except Exception:
        return "—"




def paginate_rows(rows, page_size=40):
    """Split rows into pages of page_size."""
    return [rows[i : i + page_size] for i in range(0, len(rows), page_size)]


def build_header(supplier, date):
    """
    Creates HTML header for the report with supplier and invoice date information.
    Uses escape for safely including data in HTML.
    
    Important: Telegram only supports a limited subset of HTML tags.
    Instead of <br>, we use newline character \n.
    """
    # Explicitly import escape for reliability
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
    from app.utils.formatters import format_price, format_quantity

    status_map = {"ok": "✓", "unknown": "❗"}
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
        status = item.get("status", "")
        # Подсветка UNIT если проблема только в единице измерения
        if status == "unit_mismatch":
            unit = f"<b>{unit}</b>"
        # Используем price если есть, иначе unit_price, иначе вычисляем из total/qty
        price = item.get("price", None)
        if price in (None, "", "—"):
            price = item.get("unit_price", None)
        total = item.get("total", None)
        status = item.get("status", "")
        computed_price = None
        if (price in (None, "", "—")) and (total not in (None, "", "—")) and (qty not in (None, "", "—")):
            try:
                computed_price = float(total) / float(qty)
                price_str = format_price(computed_price, decimal_places=0)
            except Exception:
                price_str = "—"
        else:
            price_str = format_price(price, decimal_places=0) if price not in (None, "", "—") else "—"
        
        # Используем унифицированный форматтер для количества
        qty_str = format_quantity(qty) if qty not in (None, "") else "—"
        
        # Столбец с флажком для нераспознанных позиций
        # Для ручного редактирования (manual) флажок не показываем
        flag = "" if status in ["ok", "manual"] else "❗"
        row = f"{str(idx):<2} {pad(name,14)}{pad(qty_str,5)}{pad(unit,5)}{pad(price_str,6)}{pad(flag,2)}"
        table_rows.append(row)

    return "\n".join(table_rows)


def build_summary(match_results):
    """
    Creates a detailed HTML report about errors for each problematic item.
    """
    from app.i18n import t
    
    errors = []
    for idx, item in enumerate(match_results, 1):
        status = item.get("status", "")
        
        # Пропускаем позиции с ручным редактированием - они не считаются ошибочными
        if status == "manual":
            continue
            
        name = item.get("name", "")
        problems = []
        if status == "unknown":
            problems.append(t("report.unknown"))
        qty = item.get("qty", None)
        price = item.get("price", None)
        if price in (None, "", "—"):
            price = item.get("unit_price", None)
        if qty in (None, "", "—"):
            problems.append(t("report.no_quantity"))
        if price in (None, "", "—"):
            problems.append(t("report.no_price"))
        if problems:
            error_line = t("report.error_line", params={"line": idx, "name": name, "problem": ', '.join(problems)})
            if not error_line.startswith("❗"):
                error_line = f"❗ Line {idx} <b>{name}</b>: {', '.join(problems)}"
            errors.append(error_line)
    
    # Считаем позиции со статусом "ok" или "manual" как правильные
    correct = sum(1 for item in match_results if item.get("status", "") == "ok")
    
    # Считаем позиции с проблемами (исключая ручное редактирование)
    issues = sum(1 for item in match_results if item.get("status", "") != "ok")
    
    if not errors:
        return f"{t('report.no_errors')}\nCorrect: {correct}\nIssues: {issues}"
    return (
        "\n".join(errors)
        + f"\nCorrect: {correct}\nIssues: {issues}"
    )

def count_issues(match_results):
    """
    Подсчитывает количество проблемных позиций в результатах матчинга,
    исключая позиции с ручным редактированием (статус "manual").
    
    Args:
        match_results: Список результатов матчинга позиций
        
    Returns:
        int: Количество проблемных позиций
    """
    return sum(1 for item in match_results if item.get("status", "") != "ok")

def build_report(parsed_data, match_results, escape_html=True, page=1, page_size=40):
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
    unit_mismatch_count = 0
    invoice_total = 0
    has_unparsed = False
    for item in match_results:
        status = item.get("status", "")
        if status == "ok":
            ok_count += 1
        elif status == "unknown":
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
    summary_html = build_summary(match_results)
    html_report = (
        f"{header_html}"
        f"<pre>{table}</pre>\n"
        f"{summary_html}"
    )
    return html_report.strip(), issues_count > 0