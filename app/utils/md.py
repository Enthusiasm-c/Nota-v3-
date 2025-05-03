import re

MDV2_SPECIALS = r'_\*\[\]\(\)~`>#+\-=|{}.!-'

def escape_md(text: str, version=2) -> str:
    r"""
    Экранирует спецсимволы Telegram MarkdownV2. 
    Аргумент version для совместимости.
    """
    # Экранируем все спецсимволы из константы
    return re.sub(r'([' + MDV2_SPECIALS + r'])', r'\\\1', text)


def escape_v2(text: str) -> str:
    r"""
    Экранирует все спецсимволы Markdown V2, 
    включая бэктики (` и ```), 
    для безопасной отправки в Telegram.
    """
    # Сначала экранируем тройные бэктики (```) до общего экранирования,
    # чтобы избежать двойного экранирования одиночных бэктиков
    text = re.sub(r'```', r'\\`\\`\\`', text)
    escaped = escape_md(text, version=2)
    return escaped
