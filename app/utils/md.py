def escape_md(text: str, version=2) -> str:
    """Экранирует спецсимволы Telegram MarkdownV2. Аргумент version для совместимости."""
    return re.sub(r'([_\*\[\]\(\)~`>#+\-=|{}.!])', r'\\\1', text)

import re

def escape_v2(text: str) -> str:
    """
    Экранирует все спецсимволы Markdown V2, включая бэктики (\`, ```), для безопасной отправки в Telegram.
    """
    # Сначала стандартное экранирование aiogram (экранирует все по спецификации Telegram)
    escaped = escape_md(text, version=2)
    # Затем экранируем тройные бэктики (```) вручную, если они есть
    # Telegram требует экранировать каждый бэктик: \`\`\`
    # Но aiogram экранирует только одиночные, поэтому заменим "```" на "\\`\\`\\`"
    escaped = re.sub(r'```', r'\\`\\`\\`', escaped)
    return escaped
