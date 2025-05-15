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
import re

from app.fsm.states import EditFree, NotaStates
from app.assistants.client import run_thread_safe_async
from app.edit.apply_intent import apply_intent
from app.formatters import report
from app.matcher import match_positions
from app.data_loader import load_products
from app.keyboards import build_main_kb
from app.converters import parsed_to_dict
from app.utils.incremental_ui import IncrementalUI
from app.utils.i18n import t

logger = logging.getLogger(__name__)

# Создаем роутер для регистрации обработчиков
router = Router()

@router.message(EditFree.awaiting_input)
@router.message(NotaStates.editing)
async def handle_free_edit_text(message: Message, state: FSMContext):
    """
    Улучшенный обработчик свободного ввода пользователя для редактирования инвойса через ядро edit_core.
    Оставляет только UI-логику и работу с IncrementalUI.
    """
    try:
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
        
        # Инициализируем переменную ui в блоке try
        try:
            ui = IncrementalUI(message.bot, message.chat.id)
        except Exception as ui_error:
            logger.error(f"[edit_flow] Не удалось создать IncrementalUI: {ui_error}")
            await message.answer(t("error.command_failed", lang=lang))
            return
            
        processing_started = False
        
        # Обработчик для отправки текста обработки
        async def send_processing(text):
            nonlocal processing_started
            if not processing_started:
                await ui.start(text)
                processing_started = True
            else:
                await ui.update(text)
        
        # Обработчик для отправки результата с клавиатурой
        result_ui = None
        has_errors_result = True
        
        async def send_result(text):
            nonlocal result_ui, has_errors_result
            result_ui = text
        
        async def send_error(text):
            await ui.error(text)
        
        async def fuzzy_suggester(message, state, name, idx, lang):
            # Здесь можно реализовать кастомный UI для fuzzy
            from app.handlers.name_picker import show_fuzzy_suggestions
            return await show_fuzzy_suggestions(message, state, name, idx, lang)
        
        async def edit_state():
            await state.set_state(EditFree.awaiting_input)

        # Отправляем сразу на OpenAI для парсинга интента
        result = await process_user_edit(
            message=message,
            state=state,
            user_text=user_text,
            lang=lang,
            send_processing=send_processing,
            send_result=send_result,
            send_error=send_error,
            fuzzy_suggester=fuzzy_suggester,
            edit_state=edit_state,
            # Не передаем локальный парсер, чтобы использовался GPT по умолчанию
            run_openai_intent=None
        )
        
        # Проверяем, что результат был получен успешно и содержит has_errors
        if result and isinstance(result, tuple) and len(result) >= 3:
            _, _, has_errors_result = result
            logger.info(f"[incremental_edit_flow] Process result: has_errors={has_errors_result}")
            
            # Отображаем финальный результат с клавиатурой
            if result_ui:
                await ui.complete_with_keyboard(result_ui, has_errors=has_errors_result, lang=lang)
                logger.info(f"[incremental_edit_flow] UI completed with keyboard, has_errors={has_errors_result}")
            else:
                logger.warning("[incremental_edit_flow] No result_ui to display")
        else:
            # Если результат не содержит has_errors, используем стандартный метод complete
            if result_ui:
                await ui.complete(result_ui)
                logger.info("[incremental_edit_flow] UI completed without keyboard")
            else:
                logger.warning("[incremental_edit_flow] No result_ui to display")
                
        await state.set_state(EditFree.awaiting_input)
        
    except Exception as e:
        logger.error("[edit_flow] Критическая ошибка при обработке команды", 
                    extra={"data": {"error": str(e)}}, exc_info=True)
        
        # Завершаем UI с сообщением об ошибке
        try:
            ui = IncrementalUI(message.bot, message.chat.id)
            await ui.error(
                "Сервис временно недоступен. Пожалуйста, попробуйте позже.\n"
                "Если проблема повторяется, обратитесь к администратору."
            )
        except Exception as ui_error:
            logger.error(f"[edit_flow] Не удалось отправить сообщение об ошибке: {ui_error}")

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
    await ui.append("• <i>строка 3 единица шт</i>")
    
    # Завершаем UI с инструкцией по отмене
    await ui.complete("Введите команду или <i>отмена</i> для возврата.")
    
    # Отвечаем на callback
    await call.answer()

# Обработчик подтверждения fuzzy-совпадения уже использует UI-обновления 
# через замену сообщения, поэтому оставляем без изменений
# ...

# Остальные обработчики тоже можно улучшить с использованием IncrementalUI