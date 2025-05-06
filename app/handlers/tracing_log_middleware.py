import time
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import Update
from app.trace_context import set_trace_id
import logging

class TracingLogMiddleware(BaseMiddleware):
    async def on_pre_process_update(self, update: Update, data: dict):
        # Генерируем trace_id: TRACE-{update_id}-{ms}
        update_id = getattr(update, 'update_id', None)
        ms = int(time.time() * 1000)
        trace_id = f"TRACE-{update_id}-{ms}"
        set_trace_id(trace_id)
        # Логируем user input (если есть)
        user_text = None
        if hasattr(update, 'message') and update.message:
            user_text = update.message.text
        elif hasattr(update, 'callback_query') and update.callback_query:
            user_text = update.callback_query.data
        logging.info("User input", extra={"trace_id": trace_id, "data": {"user_text": user_text}})
        data["trace_id"] = trace_id
