"""
Модуль для трассировки вызовов OpenAI API.
"""

import logging
from functools import wraps

from app.trace_context import get_request_id

logger = logging.getLogger(__name__)


def trace_openai(func):
    """
    Декоратор для трассировки вызовов OpenAI API.
    Добавляет request_id в параметры вызова.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        request_id = get_request_id()
        if request_id:
            kwargs['request_id'] = request_id
        logger.info(
            "OpenAI call: prompt",
            extra={"trace_id": request_id, "data": {"args": args, "kwargs": kwargs}},
        )
        try:
            result = func(*args, **kwargs)
            logger.info(
                "OpenAI call: result", extra={"trace_id": request_id, "data": {"result": result}}
            )
            return result
        except Exception as e:
            logger.error(
                "OpenAI call: exception", extra={"trace_id": request_id, "data": {"error": str(e)}}
            )
            raise

    return wrapper