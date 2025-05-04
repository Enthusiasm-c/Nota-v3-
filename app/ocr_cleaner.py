import re
import json


def extract_json_block(text: str) -> str:
    """
    Extracts the first JSON object from a string, ignoring code fences and commentary.
    Returns the JSON string or raises ValueError if not found.
    """
    # Remove code fences and 'json' labels
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"```$", "", text, flags=re.MULTILINE)
    # Find the first balanced {...} block
    brace_stack = []
    start = None
    for i, c in enumerate(text):
        if c == "{":
            if not brace_stack:
                start = i
            brace_stack.append(c)
        elif c == "}":
            if brace_stack:
                brace_stack.pop()
                if not brace_stack and start is not None:
                    return text[start : i + 1]
    raise ValueError("No JSON object found in text")


import logging


def _sanitize_json(obj):
    # Если уже ParsedData-like
    if isinstance(obj, dict):
        # Если есть positions, но нет supplier/date — добавить их как None
        if "positions" in obj:
            if "supplier" not in obj:
                obj["supplier"] = None
            if "date" not in obj:
                obj["date"] = None
            return obj
        # Если это dict-позиция
        return {"supplier": None, "date": None, "positions": [obj]}
    # Если это список позиций
    if isinstance(obj, list):
        return {"supplier": None, "date": None, "positions": obj}
    # fallback
    return {"supplier": None, "date": None, "positions": []}


def clean_ocr_response(text: str):
    """
    Cleans OpenAI OCR response and returns parsed dict.
    """
    logging.debug(f"Raw OCR answer: {text!r}")
    json_str = extract_json_block(text)
    obj = json.loads(json_str)
    return _sanitize_json(obj)
