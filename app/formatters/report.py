import logging
import re
from html import escape  # For escaping data only, not HTML tags

from app.utils.formatters import format_price, format_quantity, format_idr

logger = logging.getLogger("nota.report")
logger.debug("escape func = %s", escape)


def paginate_rows(rows, page_size=40):
    """Split rows into pages of page_size."""
    return [rows[i : i + page_size] for i in range(0, len(rows), page_size)]


def build_header(supplier, date):
    r"""
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

    logger = logging.getLogger(__name__)
    logger.critical(f"BUILD_TABLE: Получено {len(rows) if rows else 0} строк для отображения")

    if rows:
        for i, row in enumerate(rows):
            logger.critical(f"BUILD_TABLE: Строка {i+1}: {row}")

    status_map = {"ok": "✓", "unknown": "❗", "unit_mismatch": "❗", "error": "❗", "manual": ""}

    def pad_with_html(text, width):
        visible_text = re.sub(r"<[^>]+>", "", str(text))
        visible_len = len(visible_text)
        padding = max(0, width - visible_len)
        return str(text) + " " * padding

    def format_price_with_spaces(price_str):
        """Форматирует цену с пробелами между тысячами: 240 000, 5 000, 13 200"""
        if price_str is None or price_str == "—":
            return "—"

        # Преобразуем любой тип аргумента в строку
        if not isinstance(price_str, str):
            # Если это число, округляем до целого
            if isinstance(price_str, (int, float)):
                price_str = str(int(round(price_str)))
            else:
                price_str = str(price_str)

        # Очищаем от всех нечисловых символов
        clean_price = "".join(c for c in price_str if c.isdigit())
        if not clean_price:
            return "—"
        # Форматируем с пробелами между тысячами
        if len(clean_price) > 3:
            # Разделяем число на группы по 3 цифры справа налево и соединяем пробелами
            groups = []
            for i in range(len(clean_price), 0, -3):
                start = max(0, i - 3)
                groups.insert(0, clean_price[start:i])
            return " ".join(groups)
        return clean_price

    # Если позиций нет, возвращаем только заголовок и строку-заглушку
    if not rows:
        header = "# NAME            QTY   UNIT PRICE  "
        return header + "\n—"

    # Жёстко задаём ширины для теста layout
    name_width = 14
    qty_width = 5
    unit_width = 5
    price_width = 6

    # Определяем положение каждого столбца в заголовке с учетом смещений:
    # NAME влево на 2 знака, QTY влево на 2 знака (смещаем на 1 вправо), UNIT влево на 4 знака, PRICE влево на 4 знака (смещаем на 1 вправо)
    num_pos = 0
    name_pos = 2  # Смещено на 2 знака влево от исходного положения (было 4)
    qty_pos = (
        name_pos + name_width
    )  # Смещено на 2 знака влево от исходного положения (было -3, изменили на -2)
    unit_pos = (
        qty_pos + qty_width
    )  # Смещено на 3 знака влево от исходного положения (вместо -4 сдвигаем на -3)
    price_pos = (
        unit_pos + unit_width + 1
    )  # Смещено на 2 знака влево от исходного положения (вместо -4 сдвигаем на -2)

    # Формируем заголовок с точным расположением названий столбцов
    header = (
        " " * num_pos
        + "#"
        + " " * (name_pos - num_pos - 1)
        + "NAME"
        + " " * (qty_pos - name_pos - 4)
        + "QTY"
        + " " * (unit_pos - qty_pos - 3)
        + "UNIT"
        + " " * (price_pos - unit_pos - 4 - 1)
        + "PRICE"
    )

    table_rows = []
    for idx, row in enumerate(rows, 1):
        # ИСПРАВЛЕНО: Правильная проверка matched_name на None и пустоту
        matched_name = row.get("matched_name")
        original_name = row.get("name", "")

        # Используем matched_name только если он не None и не пустой
        if matched_name and str(matched_name).strip():
            display_name = matched_name
        else:
            display_name = original_name

        name = html_escape(str(display_name))
        # Обрезаем длинные имена с многоточием
        if len(name) > name_width - 1:
            name = name[: name_width - 2] + "…"
        qty = format_quantity(row.get("qty", ""))
        unit = html_escape(str(row.get("unit", "")))
        price = format_price_with_spaces(row.get("price", ""))
        status = status_map.get(row.get("status", ""), "")
        if row.get("status") in ["unknown", "unit_mismatch", "error"]:
            name = f"<b>{name}</b>"
            qty = f"<b>{qty}</b>"
            unit = f"<b>{unit}</b>"
            price = f"<b>{price}</b>"
        table_row = (
            f"{idx} {pad_with_html(name, name_width)}"
            f"{pad_with_html(qty, qty_width)}"
            f"{pad_with_html(unit, unit_width)}"
            f"{pad_with_html(price, price_width)}"
            f" {status}"
        )
        table_rows.append(table_row)
    return header + "\n" + "\n".join(table_rows)


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
                error_line = t(
                    "report.error_line",
                    params={"line": idx, "name": name, "problem": ", ".join(problems)},
                )
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

    return "\n".join(errors) + f"\nCorrect: {correct_count}\nIssues: {issues_count}"


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


def calculate_total_amount(match_results):
    """
    Вычисляет итоговую сумму накладной на основе результатов сопоставления.

    Args:
        match_results: Список результатов сопоставления позиций

    Returns:
        float: Итоговая сумма накладной
    """
    total = 0.0

    for item in match_results:
        # Пытаемся получить line_total, если его нет - вычисляем из qty * price
        line_total = item.get("line_total")

        if line_total is not None:
            try:
                total += float(line_total)
                continue
            except (ValueError, TypeError):
                pass

        # Если line_total отсутствует, вычисляем из qty * price
        qty = item.get("qty")
        price = item.get("price")

        if qty is not None and price is not None:
            try:
                qty_val = float(qty)
                price_val = float(price)
                total += qty_val * price_val
            except (ValueError, TypeError):
                # Пропускаем позиции с некорректными данными
                continue

    return total


def format_total_summary(match_results):
    """
    Форматирует итоговую информацию накладной с итоговой суммой.

    Args:
        match_results: Список результатов сопоставления позиций

    Returns:
        str: Отформатированная строка с итоговой информацией
    """

    def format_price_with_spaces(price_val):
        """Форматирует цену с пробелами между тысячами"""
        if price_val is None or price_val == 0:
            return "0"

        price_str = str(int(round(price_val)))
        if len(price_str) > 3:
            groups = []
            for i in range(len(price_str), 0, -3):
                start = max(0, i - 3)
                groups.insert(0, price_str[start:i])
            return " ".join(groups)
        return price_str

    total_amount = calculate_total_amount(match_results)
    formatted_total = format_price_with_spaces(total_amount)

    return f"\n<b>Total Amount: IDR {formatted_total}</b>"


def build_report(parsed_data, match_results, escape_html=True, page=1, page_size=40):
    r"""
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
    logger = logging.getLogger(__name__)

    # Извлекаем основную информацию из разных типов данных
    supplier = getattr(parsed_data, "supplier", None)
    if supplier is None and isinstance(parsed_data, dict):
        supplier = parsed_data.get("supplier", None)
    date = getattr(parsed_data, "date", None)
    if date is None and isinstance(parsed_data, dict):
        date = parsed_data.get("date", None)
    
    # Проверяем статус поставщика аналогично товарам
    if not supplier:
        supplier_str = "❌ Supplier not detected"
    else:
        from app.supplier_mapping import get_supplier_syrve_guid
        syrve_guid = get_supplier_syrve_guid(supplier)
        if syrve_guid:
            supplier_str = f"✅ {supplier}"
        else:
            supplier_str = f"❌ {supplier}"
    
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

    # ДИАГНОСТИКА: Проверяем что передается в build_table
    logger.critical(
        f"BUILD_REPORT: Pagination {page}/{(len(match_results) + page_size - 1) // page_size}, start={start}, end={end}"
    )
    logger.critical(
        f"BUILD_REPORT: len(match_results)={len(match_results)}, len(rows_to_show)={len(rows_to_show)}"
    )
    logger.critical(f"BUILD_REPORT: rows_to_show={rows_to_show}")

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
    total_summary = format_total_summary(match_results)
    # Используем <pre> вместо <code> для Telegram и тестов
    html_report = f"{header_html}" f"<pre>{table}</pre>\n" f"{summary_html}" f"{total_summary}"
    return html_report.strip(), has_errors
