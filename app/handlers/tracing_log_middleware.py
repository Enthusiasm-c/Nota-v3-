import time
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import Update
from app.trace_context import set_trace_id
import logging

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
        logging.info("User input", extra={"trace_id": trace_id, "data": {"user_text": user_text}})
        data["trace_id"] = trace_id
        return await handler(event, data)
