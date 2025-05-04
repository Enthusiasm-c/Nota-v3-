def escape_md(text, version=2):
    # Escapes all special characters for MarkdownV2
    # https://core.telegram.org/bots/api#markdownv2-style
    if not isinstance(text, str):
        text = str(text)
    specials = r"_*[]()~`>#+-=|{}.!"
    for c in specials:
        text = text.replace(c, f"\\{c}")
    return text

# Fixed column widths
W_IDX, W_NAME, W_QTY, W_UNIT, W_PRICE, W_STATUS = 3, 22, 6, 6, 9, 12

def _row(idx, name, qty, unit, price, status):
    name = (name[:W_NAME-1] + "…") if len(name) > W_NAME else name
    # Корректно форматируем price
    try:
        price_val = float(price)
        price_str = f"{price_val:,.0f}"
    except (TypeError, ValueError):
        price_str = "—"
    return (
        f"{str(idx).ljust(W_IDX)}"
        f"{name.ljust(W_NAME)}"
        f"{str(qty).rjust(W_QTY)} "
        f"{unit.ljust(W_UNIT)} "
        f"{price_str.rjust(W_PRICE)} "
        f"{status}"
    )

def build_table(rows: list[str]) -> str:
    header = _row("#", "NAME", "QTY", "UNIT", "PRICE", "STATUS")
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
            supplier_str = "Unknown supplier" if not supplier else escape_md(str(supplier), version=2)
            date_str = "—" if not date else escape_md(str(date), version=2)
        else:
            supplier_str = "Unknown supplier" if not supplier else str(supplier)
            date_str = "—" if not date else str(date)
            
        # Подсчитываем статистику по позициям
        ok_count = sum(1 for r in match_results if r.get("status") == "ok")
        unit_mismatch_count = sum(1 for r in match_results if r.get("status") == "unit_mismatch")
        unknown_count = sum(1 for r in match_results if r.get("status") == "unknown")
        need_check_count = unit_mismatch_count + unknown_count
        
        # Формируем заголовок
        report = (
            f"\U0001F4E6 *Supplier:* {supplier_str}\n"
            f"\U0001F4C6 *Invoice date:* {date_str}\n"
        )
        report += "────────────────────────────────────────\n"
        
        # Создаем строки для таблицы позиций
        rows = []
        for idx, r in enumerate(match_results, 1):
            # Получаем данные позиции, предотвращая ошибки с None
            name = str(r.get("name", "")) if r.get("name") is not None else ""
            qty = str(r.get("qty", "")) if r.get("qty") is not None else ""
            unit = str(r.get("unit", "")) if r.get("unit") is not None else ""
            price = r.get("price")
            status = r.get("status", "unknown")
            
            # Экранируем значения, если нужно
            if escape:
                name = escape_md(name, version=2)
                qty = escape_md(qty, version=2)
                unit = escape_md(unit, version=2)
                
            # Определяем строку статуса
            if status == "ok":
                status_str = "✅ ok"
            elif status == "unit_mismatch":
                status_str = "⚖️ unit mismatch"
            elif status == "unknown":
                status_str = "❓ not found"
            else:
                status_str = escape_md(str(status), version=2) if escape else str(status)
                
            # Добавляем строку в таблицу
            rows.append(_row(idx, name, qty, unit, price, status_str))
            
        # Добавляем таблицу в отчет (в блоке кода для сохранения форматирования)
        report += build_table(rows) + "\n"
        report += "────────────────────────────────────────\n"
        
        # Добавляем итоговую статистику (не показываем "0 ок" и т.п.)
        summary = []
        if ok_count > 0:
            summary.append(f"✅ {ok_count} ok")
        if unit_mismatch_count > 0:
            summary.append(f"⚖️ {unit_mismatch_count} unit mismatch")
        if unknown_count > 0:
            summary.append(f"❓ {unknown_count} not found")
        if summary:
            report += "        ".join(summary)
            
        return report.strip()
        
    except Exception as e:
        # Логируем ошибку и возвращаем минимальную безопасную информацию
        logger.error(f"Error building report: {e}")
        
        # Формируем минимальный отчет, который точно не вызовет ошибку форматирования
        basic_report = f"Found {len(match_results)} positions.\n"
        basic_report += f"Complete: {ok_count}, Need verification: {need_check_count}"
        
        return basic_report
