import time
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import Update
from app.trace_context import set_trace_id
import logging
import json

# Универсальный сериализатор для Pydantic и сложных объектов
def _default(o):
    if hasattr(o, 'model_dump'):
        return o.model_dump()
    return str(o)

class TracingLogMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        # Генерируем trace_id: TRACE-{update_id}-{ms}
        update_id = getattr(event, 'update_id', None)
        ms = int(time.time() * 1000)
        trace_id = f"TRACE-{update_id}-{ms}"
        set_trace_id(trace_id)
        # Логируем user input (если есть)
        user_text = None
        if hasattr(event, 'message') and event.message:
            user_text = event.message.text
        elif hasattr(event, 'callback_query') and event.callback_query:
            user_text = event.callback_query.data
        # Безопасное логирование: сериализация сложных объектов
        try:
            # Универсальная сериализация через json + _default
            log_entry = {"trace_id": trace_id, "data": {"user_text": user_text}}
            logging.info("User input: %s", json.dumps(log_entry, default=_default, ensure_ascii=False))
        except Exception as e:
            logging.info("User input (fallback)", extra={"trace_id": trace_id, "data": {"user_text": str(user_text), "error": str(e)}})
        data["trace_id"] = trace_id
        return await handler(event, data)
