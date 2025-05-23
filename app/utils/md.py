import html
import logging
import re

logger = logging.getLogger(__name__)


def escape_html(text: str) -> str:
    """
    Экранирует спецсимволы для HTML
    (используется для Telegram HTML parse_mode).

    Args:
        text: Исходный текст для экранирования

    Returns:
        str: Экранированный текст, безопасный для HTML
    """
    if text is None:
        return ""
    try:
        return html.escape(text)
    except Exception as e:
        logger.error(f"Error escaping HTML: {e}, text: {text[:100]}...")
        return str(text)  # Возвращаем строковое представление на случай, если это не строка


def clean_html(text: str) -> str:
    """
    Удаляет HTML-теги из текста, не меняя содержимое.
    Полезно при ошибках форматирования в Telegram.

    Args:
        text: Исходный текст с HTML-тегами

    Returns:
        str: Текст без HTML-тегов
    """
    if text is None:
        return ""
    try:
        # Сначала заменяем специальные HTML-сущности
        text = text.replace("&nbsp;", " ")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&amp;", "&")
        text = text.replace("&quot;", '"')

        # Затем удаляем HTML-теги
        text = re.sub(r"<[^>]+>", "", text)

        # Удаляем Markdown-код если он случайно попал в текст
        text = text.replace("```diff", "")
        text = text.replace("```", "")

        return text
    except Exception as e:
        logger.error(f"Error removing HTML tags: {e}, text: {text[:100]}...")
        return text


def escape_v2(text: str) -> str:
    """
    Экранирует спецсимволы для MarkdownV2 (Telegram parse_mode=MarkdownV2).
    Не экранирует внутри блоков кода (```).

    Args:
        text: Исходный текст с Markdown разметкой

    Returns:
        str: Текст с экранированными специальными символами
    """
    if text is None:
        return ""
    try:
        # Экранируемые символы MarkdownV2
        md_chars = r"[_*\[\]()~`>#+\-=|{}.!]"
        # Регулярка для блоков кода
        code_block = re.compile(r"```.*?```", re.DOTALL)
        parts = []
        last_end = 0
        for m in code_block.finditer(text):
            # Экранируем вне блока кода
            before = text[last_end : m.start()]
            before = re.sub(md_chars, lambda m: "\\" + m.group(0), before)
            parts.append(before)
            parts.append(m.group(0))
            last_end = m.end()
        # Последний кусок
        tail = text[last_end:]
        tail = re.sub(md_chars, lambda m: "\\" + m.group(0), tail)
        parts.append(tail)
        return "".join(parts)
    except Exception as e:
        logger.error(f"Error escaping MarkdownV2: {e}, text: {text[:100]}...")
        return text  # Возвращаем исходный текст при ошибке
