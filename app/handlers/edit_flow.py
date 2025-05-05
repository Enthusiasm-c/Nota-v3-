"""
Обработчики для потока редактирования инвойса через GPT-3.5-turbo.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from app.fsm.states import EditFree
from app.assistants.client import run_thread_safe
from app.edit.apply_intent import apply_intent
from app.formatters import report
from app.matcher import match_positions
from app.data_loader import load_products
from app.keyboards import build_main_kb

logger = logging.getLogger(__name__)

# Создаем роутер для регистрации обработчиков
router = Router()

@router.message(EditFree.awaiting_input)
async def handle_free_edit_text(message: Message, state: FSMContext):
    """
    Обработчик свободного ввода пользователя в режиме редактирования.
    Использует GPT-3.5-turbo для разбора естественного языка.
    
    Args:
        message: Входящее сообщение Telegram
        state: FSM-контекст
    """
    user_text = message.text.strip()
    
    # Получаем данные из состояния
    data = await state.get_data()
    invoice = data.get("invoice")
    
    if not invoice:
        await message.answer("Сессия истекла. Пожалуйста, загрузите инвойс заново.")
        await state.clear()
        return
    
    try:
        # Отправляем текст пользователя в OpenAI Assistant
        intent = run_thread_safe(user_text)
    except Exception as e:
        logger.warning(f"Не удалось разобрать команду: {e}")
        intent = {"action": "unknown", "error": str(e)}
    
    # Проверяем успешность разбора
    if intent.get("action") == "unknown":
        error = intent.get("error", "unknown_error")
        logger.warning(f"Не удалось разобрать команду: {error}")
        await message.answer(
            "Не понял, что нужно изменить. Попробуйте переформулировать, например:\n"
            "• дата 16 апреля\n"
            "• строка 2 цена 95000"
        )
        return
    
    # Применяем интент к инвойсу
    new_invoice = apply_intent(invoice, intent)
    
    # Пересчитываем ошибки и обновляем отчёт
    match_results = match_positions(new_invoice["positions"], load_products())
    text, has_errors = report.build_report(new_invoice, match_results)
    
    # Подсчитываем количество оставшихся проблем
    issues_count = sum(1 for item in match_results if item.get("status", "") != "ok")
    
    # Обновляем данные в состоянии
    await state.update_data(invoice=new_invoice, issues_count=issues_count)
    
    # Генерируем клавиатуру в зависимости от наличия ошибок
    keyboard = build_main_kb(has_errors)
    
    # Отправляем обновлённый отчёт
    await message.answer(
        text, 
        reply_markup=keyboard, 
        parse_mode="HTML"
    )
    
    # Добавляем сообщение об успешном редактировании
    if not has_errors:
        await message.answer("✅ Все ошибки исправлены! Вы можете подтвердить инвойс.")
    
    # Остаёмся в том же состоянии для продолжения редактирования
    await state.set_state(EditFree.awaiting_input)

# Обработчик нажатия кнопки "✏️ Редактировать"
@router.callback_query(F.data == "edit:free")
async def handle_edit_free(call: CallbackQuery, state: FSMContext):
    """
    Обработчик кнопки "✏️ Редактировать".
    Переводит пользователя в режим свободного редактирования.
    """
    # Переходим в состояние ожидания ввода
    await state.set_state(EditFree.awaiting_input)
    
    # Отправляем инструкцию
    await call.message.answer(
        "Что нужно отредактировать? Примеры команд:\n\n"
        "• <i>дата 16 апреля</i>\n"
        "• <i>строка 2 цена 95000</i>\n"
        "• <i>строка 1 название Apple</i>\n"
        "• <i>строка 3 количество 10</i>\n\n"
        "Введите команду или <i>отмена</i> для возврата.",
        parse_mode="HTML"
    )
    
    # Отвечаем на callback
    await call.answer()