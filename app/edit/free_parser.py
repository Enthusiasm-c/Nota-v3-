import re
from datetime import date
from typing import Any, Dict

# Примеры шаблонов для MVP
DATE_PATTERNS = [
    r"дата\s*[—-]?\s*(.+)",
    r"invoice date\s*[—-]?\s*(.+)",
]
LINE_EDIT_PATTERN = r"строка\s*(\d+)\s*(name|qty|unit|price|имя|кол-во|единица|цена)\s+(.+)"
REMOVE_PATTERN = r"(удали|игнор)\s*(\d+)"
ADD_PATTERN = r"добав(ь|ить)?\s+(.+)"
FINISH_PATTERN = r"^(готово|все исправил|finish|done)$"


def detect_intent(text: str) -> Dict[str, Any]:
    orig_text = text.strip()
    text_lc = orig_text.lower()
    # 1. Date edit
    for pat in DATE_PATTERNS:
        m = re.match(pat, text_lc)
        if m:
            return {"action": "edit_date", "value": m.group(1)}
    # 2. Line field edit
    m = re.match(LINE_EDIT_PATTERN, text_lc)
    if m:
        return {"action": "edit_line_field", "line": int(m.group(1)), "field": m.group(2), "value": m.group(3)}
    # 3. Remove/ignore line
    m = re.match(REMOVE_PATTERN, text_lc)
    if m:
        return {"action": "remove_line", "line": int(m.group(2))}
    # 4. Add new line
    m = re.match(ADD_PATTERN, text_lc)
    if m:
        # Возвращаем исходный текст (с регистром) после команды "добавь"
        match = re.match(ADD_PATTERN, orig_text, re.IGNORECASE)
        value = match.group(2) if match else m.group(2)
        return {"action": "add_line", "value": value}
    # 5. Finish
    m = re.match(FINISH_PATTERN, text_lc)
    if m:
        return {"action": "finish"}
    # Не распознано
    return {"action": "unknown"}


def apply_edit(ctx: dict, intent: dict) -> dict:
    """
    Применяет изменения к инвойсу (ctx) согласно intent.
    Возвращает новый ctx (invoice dict).
    """
    from copy import deepcopy
    invoice = deepcopy(ctx)
    positions = invoice.get("positions", [])
    action = intent.get("action")
    if action == "edit_date":
        invoice["date"] = intent["value"].strip()
    elif action == "edit_line_field":
        # Редактируем поле строки
        idx = intent["line"] - 1
        field = intent["field"]
        value = intent["value"]
        # Маппинг русских полей к внутренним ключам
        field_map = {
            "цена": "price",
            "имя": "name",
            "кол-во": "qty",
            "единица": "unit",
            "price": "price",
            "name": "name",
            "qty": "qty",
            "unit": "unit",
        }
        field = field_map.get(field, field)
        new_ctx = deepcopy(ctx)
        if 0 <= idx < len(new_ctx["positions"]):
            new_ctx["positions"][idx][field] = value
        return new_ctx
    elif action == "remove_line":
        idx = intent["line"] - 1
        if 0 <= idx < len(positions):
            positions.pop(idx)
        invoice["positions"] = positions
    elif action == "add_line":
        # Ожидаем строку вида 'name qty unit price'
        parts = intent["value"].split()
        if len(parts) >= 4:
            name = " ".join(parts[:-3])
            qty = parts[-3]
            unit = parts[-2]
            price = parts[-1]
            positions.append({
                "name": name,
                "qty": qty,
                "unit": unit,
                "price": price
            })
            invoice["positions"] = positions
    # Для finish и unknown — ничего не делаем
    return invoice
