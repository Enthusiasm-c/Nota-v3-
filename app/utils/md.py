import html
import re


def escape_html(text: str) -> str:
    """
    Экранирует спецсимволы для HTML 
    (используется для Telegram HTML parse_mode).
    """
    if text is None:
        return ""
    return html.escape(text)


def escape_v2(text: str) -> str:
    """
    Экранирует спецсимволы для MarkdownV2 (Telegram parse_mode=MarkdownV2).
    Не экранирует внутри блоков кода (```).
    """
    if text is None:
        return ""
    # Экранируемые символы MarkdownV2
    md_chars = r"[_*\[\]()~`>#+\-=|{}.!]"
    # Регулярка для блоков кода
    code_block = re.compile(r"```.*?```", re.DOTALL)
    parts = []
    last_end = 0
    for m in code_block.finditer(text):
        # Экранируем вне блока кода
        before = text[last_end:m.start()]
        before = re.sub(md_chars, lambda m: '\\' + m.group(0), before)
        parts.append(before)
        parts.append(m.group(0))
        last_end = m.end()
    # Последний кусок
    tail = text[last_end:]
    tail = re.sub(md_chars, lambda m: '\\' + m.group(0), tail)
    parts.append(tail)
    return ''.join(parts)
