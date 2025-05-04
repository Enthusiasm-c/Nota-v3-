import html


def escape_html(text: str) -> str:
    """
    Экранирует спецсимволы для HTML 
    (используется для Telegram HTML parse_mode).
    """
    if text is None:
        return ""
    return html.escape(text)
