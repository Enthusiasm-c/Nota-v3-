from html import escape  # For escaping data only, not HTML tags
import logging
logging.getLogger("nota.report").debug("escape func = %s", escape)
from decimal import Decimal
from app.utils.formatters import format_price, format_quantity
import re

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
    Проблемные значения выделяются жирным шрифтом.
    """
    from html import escape as html_escape
    from app.utils.formatters import format_price, format_quantity

    status_map = {"ok": "✓", "unknown": "❗", "unit_mismatch": "❗", "error": "❗", "manual": ""}
    
    # Функция для выравнивания текста с учетом HTML-тегов
    def pad_with_html(text, width):
        # Удаляем HTML-теги для расчета видимой длины
        visible_text = re.sub(r'<[^>]+>', '', str(text))
        visible_len = len(visible_text)
        # Добавляем пробелы, учитывая разницу между видимой и полной длиной текста
        padding = max(0, width - visible_len)
        return f"{text}{' ' * padding}"

    header = f"#  {'NAME'.ljust(14)}{'QTY'.ljust(5)}{'UNIT'.ljust(5)}{'PRICE'.ljust(6)}! "
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
        
        # Выделение имени если есть проблема с распознаванием товара
        if status == "unknown":
            name = f"<b>{name}</b>"
        
        # Подсветка UNIT если проблема в единице измерения
        if status == "unit_mismatch":
            unit = f"<b>{unit}</b>"
            
        # Используем price если есть, иначе unit_price, иначе вычисляем из total/qty
        price = item.get("price", None)
        if price in (None, "", "—"):
            price = item.get("unit_price", None)
        total = item.get("total", None)
        
        # Проверка на проблемы с значениями qty или price
        has_qty_problem = qty in (None, "", "—")
        has_price_problem = price in (None, "", "—") and total in (None, "", "—")
        
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
        
        # Отображаем проблемные значения жирным шрифтом
        if has_qty_problem:
            qty_str = f"<b>{qty_str}</b>"
        if has_price_problem:
            price_str = f"<b>{price_str}</b>"
        
        # Столбец с флажком для проблемных позиций
        # Если статус не ОК и не manual, или есть проблемы с qty/price, показываем восклицательный знак
        flag = ""
        if status not in ["ok", "manual"] or has_qty_problem or has_price_problem:
            flag = "❗"
        
        # Используем новую функцию выравнивания с учетом HTML-тегов
        row = f"{str(idx):<2} {pad_with_html(name, 14)}{pad_with_html(qty_str, 5)}{pad_with_html(unit, 5)}{pad_with_html(price_str, 6)}{flag}"
        table_rows.append(row)

    return "\n".join(table_rows)


def build_summary(match_results):
    """
    Creates a detailed HTML report about errors for each problematic item.
    """
    from app.i18n import t
    
    errors = []
    # Счетчики для расчета числа корректных и проблемных позиций
    correct_count = 0
    issues_count = 0
    
    for idx, item in enumerate(match_results, 1):
        status = item.get("status", "")
        has_problems = False
        
        # Пропускаем позиции с ручным редактированием - они не считаются ошибочными
        if status == "manual":
            correct_count += 1
            continue
            
        name = item.get("name", "")
        problems = []
        error_details = []
        
        # Добавляем описание проблемы в зависимости от статуса
        if status == "unknown":
            problems.append(t("report.name_error") or "item not recognized (name error)")
            error_details.append("check name")
            has_problems = True
        elif status == "unit_mismatch":
            problems.append(t("report.unit_mismatch") or "unit mismatch error")
            error_details.append("check unit")
            has_problems = True
        elif status == "error":
            problems.append(t("report.processing_error") or "line processing error")
            error_details.append("processing error")
            has_problems = True
        elif status == "ok":
            # Изначально считаем позицию корректной, но перепроверим наличие количества и цены
            pass
            
        # Проверка отсутствия критических данных
        qty = item.get("qty", None)
        price = item.get("price", None)
        if price in (None, "", "—"):
            price = item.get("unit_price", None)
        
        if qty in (None, "", "—"):
            problems.append(t("report.no_quantity") or "quantity not specified")
            error_details.append("missing quantity")
            has_problems = True
        if price in (None, "", "—"):
            problems.append(t("report.no_price") or "price not specified")
            error_details.append("missing price")
            has_problems = True
            
        # Проверка автокоррекции цены
        if "auto_fixed" in item and item.get("auto_fixed", False):
            if "original_price" in item and "price" in item:
                original_price = item.get("original_price")
                corrected_price = item.get("price")
                error_details.append(f"price fixed: {corrected_price}")
                
        # Проверка ошибок валидации
        # Арифметические ошибки
        if "issues" in item:
            for issue in item.get("issues", []):
                issue_type = issue.get("type", "")
                if issue_type == "ARITHMETIC_ERROR":
                    error_details.append("check math")
                elif issue_type == "PRICE_ZERO_LOST":
                    error_details.append(f"price missing 0: {issue.get('fix', '')}")
                elif issue_type == "PRICE_EXTRA_ZERO":
                    error_details.append(f"price has extra 0: {issue.get('fix', '')}")
                elif issue_type == "QTY_DECIMAL_MISSED":
                    error_details.append(f"quantity fixed: {issue.get('fix', '')}")
                elif issue_type == "PRICE_TOO_LOW":
                    error_details.append("price too low")
                elif issue_type == "PRICE_TOO_HIGH": 
                    error_details.append("price too high")
                elif issue_type == "UNIT_MISMATCH":
                    if "suggestion" in issue:
                        error_details.append(f"should be {issue.get('suggestion', '')}")
        
        # Если нет проблем, увеличиваем счетчик корректных позиций
        if not has_problems and status == "ok":
            correct_count += 1
        else:
            issues_count += 1
            
        # Добавляем строку ошибки если есть проблемы
        if problems or error_details:
            # Используем краткое англоязычное описание ошибок, если есть
            if error_details:
                error_line = f"⚠️ Line {idx} <b>{name}</b>: {', '.join(error_details)}"
                errors.append(error_line)
            else:
                error_line = t("report.error_line", params={"line": idx, "name": name, "problem": ', '.join(problems)})
                if not error_line.startswith("❗") and not error_line.startswith("⚠️"):
                    error_line = f"⚠️ Line {idx} <b>{name}</b>: {', '.join(problems)}"
                errors.append(error_line)
        elif has_problems:
            # Если есть проблемы, но нет конкретного описания
            error_line = f"⚠️ Line {idx} <b>{name}</b>: {t('report.needs_verification') or 'needs verification'}"
            errors.append(error_line)
    
    # Если нет ошибок, показываем соответствующее сообщение
    if not errors and issues_count == 0:
        return f"{t('report.no_errors') or '<b>No errors. All items recognized correctly.</b>'}\nCorrect: {correct_count}\nIssues: {issues_count}"
    
    return (
        "\n".join(errors)
        + f"\nCorrect: {correct_count}\nIssues: {issues_count}"
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

    # Подсчитываем количество ошибок и проблем перед формированием отчёта
    ok_count = 0
    issues_count = 0
    has_errors = False
    
    for item in match_results:
        status = item.get("status", "")
        
        # Позиции с ручным редактированием (manual) не считаются проблемными
        if status == "ok" or status == "manual":
            ok_count += 1
        else:
            issues_count += 1
            has_errors = True
            
        # Проверяем наличие незаполненных данных (qty, price)
        qty = item.get("qty", None)
        price = item.get("price", None)
        if price in (None, "", "—"):
            price = item.get("unit_price", None)
            
        # Если хотя бы одно из критически важных полей не заполнено, считаем позицию проблемной
        if qty in (None, "", "—") or price in (None, "", "—"):
            has_errors = True
            # Если позиция ещё не была подсчитана как проблемная, учитываем её
            if status == "ok" or status == "manual":
                issues_count += 1
                ok_count -= 1  # корректируем счётчик OK позиций
    
    header_html = build_header(supplier_str, date_str)
    table = build_table(rows_to_show)
    summary_html = build_summary(match_results)
    
    # Используем <code> вместо <pre> для таблицы, чтобы улучшить совместимость с Telegram
    html_report = (
        f"{header_html}"
        f"<code>{table}</code>\n"
        f"{summary_html}"
    )
    return html_report.strip(), has_errors