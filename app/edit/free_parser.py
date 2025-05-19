import re
from typing import Any, Dict

# Примеры шаблонов для MVP
DATE_PATTERNS = [
    r"дата\s*[—-]?\s*(.+)",
    r"invoice date\s*[—-]?\s*(.+)",
]
WORD_NUMS = {
    "один": 1, "два": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "10": 10
}
FIELD_SYNONYMS = {
    "название": "name", "наименование": "name", "имя": "name",
    "кол-во": "qty", "количество": "qty",
    "единица": "unit", "ед": "unit",
    "цена": "price",
    "name": "name", "qty": "qty", "unit": "unit", "price": "price"
}
LINE_EDIT_PATTERN = r"строка\s*(\w+)\s*(name|qty|unit|price|имя|кол-во|единица|цена|название|наименование|количество|ед|единиц[аы]|имя)\s+(.+)"
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
        line_raw = m.group(1)
        field_raw = m.group(2)
        value = m.group(3)
        # Поддержка числительных словами
        line = WORD_NUMS.get(line_raw, None)
        if line is None:
            try:
                line = int(line_raw)
            except Exception:
                line = None
        # Поддержка синонимов полей
        field = FIELD_SYNONYMS.get(field_raw, field_raw)
        if line is not None:
            return {"action": "edit_line_field", "line": line, "field": field, "value": value}
    # 3. Remove/ignore line
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
        field_map = FIELD_SYNONYMS
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
