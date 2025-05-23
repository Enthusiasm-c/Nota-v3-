"""
Контекст для отслеживания запросов.
"""

import contextvars

# Контекстная переменная для хранения ID запроса
request_id_var = contextvars.ContextVar("request_id", default=None)


def get_request_id() -> str:
    """
    Получить ID текущего запроса.
    """
    return request_id_var.get()


def set_request_id(request_id: str) -> None:
    """
    Установить ID текущего запроса.
    """
    request_id_var.set(request_id)


def reset_request_id() -> None:
    """
    Сбросить ID текущего запроса.
    """
    request_id_var.set(None)