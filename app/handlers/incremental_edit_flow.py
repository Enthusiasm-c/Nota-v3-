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
    Улучшенный обработчик свободного ввода пользователя в режиме редактирования
    с использованием IncrementalUI для отображения прогресса.
    
    Args:
        message: Входящее сообщение Telegram
        state: FSM-контекст
    """
    user_text = message.text.strip()
    logger.info("[edit_flow] Новый ввод пользователя", extra={"data": {"user_text": user_text}})
    
    # Обработка команды отмены
    if user_text.lower() in ["отмена", "cancel"]:
        await message.answer("Редактирование отменено.")
        await state.set_state(None)  # Возвращаемся в начальное состояние
        return
    
    # Получаем данные из состояния
    data = await state.get_data()
    logger.info("[edit_flow] State at handler start", extra={"data": data})
    invoice = data.get("invoice")
    
    if not invoice:
        logger.warning("[edit_flow] Нет инвойса в состоянии пользователя")
        await message.answer("Сессия истекла. Пожалуйста, загрузите инвойс заново.")
        await state.clear()
        return
    
    # Создаем и запускаем IncrementalUI
    ui = IncrementalUI(message.bot, message.chat.id)
    await ui.start("🔍 Анализирую запрос...")
    
    try:
        # Запускаем анимированный спиннер для красивой индикации
        await ui.start_spinner()
        
        # Шаг 1: Отправка текста пользователя в OpenAI
        logger.info("[edit_flow] Отправка текста пользователя в OpenAI", 
                    extra={"data": {"user_text": user_text}})
        
        # Небольшая задержка для демонстрации спиннера (можно убрать в продакшн)
        await asyncio.sleep(0.8)
        
        # Обновляем UI перед отправкой запроса
        ui.stop_spinner()
        await ui.update("🧠 Определение необходимых изменений...")
        
        # Запускаем спиннер снова для процесса определения интента
        await ui.start_spinner()
        
        # Запрос к OpenAI для определения интента
        intent = await run_thread_safe_async(user_text)
        logger.info("[edit_flow] Ответ OpenAI получен", extra={"data": {"intent": intent}})
        
        # Обрабатываем случай неизвестного интента
        if intent.get("action") == "unknown":
            error = intent.get("error", "unknown_error")
            logger.warning("[edit_flow] Не удалось разобрать команду", 
                          extra={"data": {"error": error}})
            
            # Используем пользовательское сообщение об ошибке, если оно есть
            error_message = intent.get("user_message", 
                "Не понял, что нужно изменить. Попробуйте переформулировать, например:\n"
                "• дата 16 апреля\n"
                "• строка 2 цена 95000"
            )
            
            # Завершаем UI с сообщением об ошибке
            await ui.error(error_message)
            return
        
        # Останавливаем спиннер и обновляем UI
        ui.stop_spinner()
        await ui.update("✅ Команда распознана")
        
        # Шаг 2: Применение интента к инвойсу
        action_name = {
            "set_date": "дату",
            "set_price": "цену",
            "set_name": "название",
            "set_quantity": "количество",
            "set_unit": "единицу измерения",
            "add_line": "новую позицию"
        }.get(intent.get("action", ""), "значение")
        
        await ui.append(f"📝 Изменяю {action_name}...")
        
        # Приведение invoice к dict через универсальный адаптер
        invoice = parsed_to_dict(invoice)
        
        # Применяем интент к инвойсу
        new_invoice = apply_intent(invoice, intent)
        
        # Шаг 3: Пересчет ошибок и обновление отчета
        await ui.update("🔄 Обновляю отчет...")
        
        # Пересчитываем ошибки и обновляем отчёт
        match_results = match_positions(new_invoice["positions"], load_products())
        text, has_errors = report.build_report(new_invoice, match_results)
    
        # Проверяем есть ли какие-то неизвестные позиции
        for idx, item in enumerate(match_results):
            if item.get("status") == "unknown":
                name_to_check = item.get("name", "")
                # Ищем ближайшее совпадение
                result = fuzzy_process.extractOne(name_to_check, 
                                                [p.name for p in load_products()], 
                                                score_cutoff=82)
                
                if result:
                    suggestion, score = result[0], result[1]
                    # Сохраняем оригинал и подсказку в state для дальнейшей логики
                    await state.update_data(
                        fuzzy_original=name_to_check, 
                        fuzzy_match=suggestion,
                        fuzzy_line=idx
                    )
                    
                    # Завершаем UI с предложением исправления
                    keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="✓ Да", callback_data=f"fuzzy:confirm:{idx}"
                                ),
                                InlineKeyboardButton(
                                    text="✗ Нет", callback_data=f"fuzzy:reject:{idx}"
                                )
                            ]
                        ]
                    )
                    
                    await ui.complete(f"Наверное, вы имели в виду <b>{suggestion}</b>?", keyboard)
                    
                    # Подсчитываем количество оставшихся проблем и обновляем state
                    issues_count = sum(1 for item in match_results 
                                     if item.get("status", "") != "ok")
                    await state.update_data(invoice=new_invoice, issues_count=issues_count)
                    return  # Выходим, чтобы пользователь мог подтвердить/отклонить предложение
        
        # Подсчитываем количество оставшихся проблем
        issues_count = sum(1 for item in match_results if item.get("status", "") != "ok")
    
        # Обновляем данные в состоянии
        await state.update_data(invoice=new_invoice, issues_count=issues_count)
    
        # Генерируем клавиатуру в зависимости от наличия ошибок
        keyboard = build_main_kb(has_errors)
    
        # Добавляем сообщение об успешном редактировании
        success_message = f"✅ {action_name.capitalize()} успешно изменена!"
        if not has_errors:
            success_message += " Вы можете подтвердить инвойс."
            
        # Завершаем UI с сообщением об успехе
        await ui.complete(success_message)
        
        # Отправляем обновлённый отчёт отдельным сообщением
        await message.answer(
            text, 
            reply_markup=keyboard, 
            parse_mode="HTML"
        )
    
        # Остаёмся в том же состоянии для продолжения редактирования
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