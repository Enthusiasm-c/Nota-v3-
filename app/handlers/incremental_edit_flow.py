"""
Улучшенная версия обработчиков edit_flow.py с использованием IncrementalUI.

Этот модуль демонстрирует, как интегрировать IncrementalUI в существующие
обработчики для обеспечения прогрессивных обновлений интерфейса.
"""

import logging
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from rapidfuzz import process as fuzzy_process

from app.fsm.states import EditFree
from app.assistants.client import run_thread_safe_async
from app.edit.apply_intent import apply_intent
from app.formatters import report
from app.matcher import match_positions
from app.data_loader import load_products
from app.keyboards import build_main_kb
from app.converters import parsed_to_dict
from app.utils.incremental_ui import IncrementalUI

logger = logging.getLogger(__name__)

# Создаем роутер для регистрации обработчиков
router = Router()

@router.message(EditFree.awaiting_input)
async def handle_free_edit_text(message: Message, state: FSMContext):
    """
    Улучшенный обработчик свободного ввода пользователя для редактирования инвойса через ядро edit_core.
    Оставляет только UI-логику и работу с IncrementalUI.
    """
    logger.info(f"[incremental_edit_flow] Received update type: {type(message).__name__}")
    if not hasattr(message, 'text') or message.text is None:
        logger.warning("[incremental_edit_flow] Received message without text field")
        return
    if not message.text.strip():
        logger.debug("[incremental_edit_flow] Skipping empty message")
        return
    user_text = message.text.strip()
    data = await state.get_data()
    lang = data.get("lang", "ru")

    from app.handlers.edit_core import process_user_edit
    from app.utils.incremental_ui import IncrementalUI
    ui = IncrementalUI(message.bot, message.chat.id)
    processing_started = False
    async def send_processing(text):
        nonlocal processing_started
        if not processing_started:
            await ui.start(text)
            processing_started = True
        else:
            await ui.update(text)
    async def send_result(text):
        await ui.complete(text)
    async def send_error(text):
        await ui.error(text)
    async def fuzzy_suggester(message, state, name, idx, lang):
        # Здесь можно реализовать кастомный UI для fuzzy
        from app.handlers.name_picker import show_fuzzy_suggestions
        return await show_fuzzy_suggestions(message, state, name, idx, lang)
    async def edit_state():
        await state.set_state(EditFree.awaiting_input)

    await process_user_edit(
        message=message,
        state=state,
        user_text=user_text,
        lang=lang,
        send_processing=send_processing,
        send_result=send_result,
        send_error=send_error,
        fuzzy_suggester=fuzzy_suggester,
        edit_state=edit_state
    )
    await state.set_state(EditFree.awaiting_input)
        
    except Exception as e:
        logger.error("[edit_flow] Критическая ошибка при обработке команды", 
                    extra={"data": {"error": str(e)}}, exc_info=True)
        
        # Завершаем UI с сообщением об ошибке
        await ui.error(
            "Сервис временно недоступен. Пожалуйста, попробуйте позже.\n"
            "Если проблема повторяется, обратитесь к администратору."
        )

# Обработчик нажатия кнопки "✏️ Редактировать"
@router.callback_query(F.data == "edit:free")
async def handle_edit_free(call: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "✏️ Редактировать".
    Переводит пользователя в режим свободного редактирования.
    """
    # Явно сохраняем invoice в state при переходе в режим редактирования
    data = await state.get_data()
    invoice = data.get("invoice")
    if invoice:
        await state.update_data(invoice=invoice)
    # Переходим в состояние ожидания ввода
    await state.set_state(EditFree.awaiting_input)
    
    # Используем простую версию UI для показа инструкции
    ui = IncrementalUI(call.message.bot, call.message.chat.id)
    await ui.start("✏️ Режим редактирования")
    
    # Добавляем инструкции по каждой команде
    await ui.append("Примеры команд:")
    await ui.append("• <i>дата 16 апреля</i>")
    await ui.append("• <i>строка 2 цена 95000</i>")
    await ui.append("• <i>строка 1 название Apple</i>")
    await ui.append("• <i>строка 3 количество 10</i>")
    
    # Завершаем UI с инструкцией по отмене
    await ui.complete("Введите команду или <i>отмена</i> для возврата.")
    
    # Отвечаем на callback
    await call.answer()

# Обработчик подтверждения fuzzy-совпадения уже использует UI-обновления 
# через замену сообщения, поэтому оставляем без изменений
# ...

# Остальные обработчики тоже можно улучшить с использованием IncrementalUI