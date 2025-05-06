"""
Обработчики для потока редактирования инвойса через GPT-3.5-turbo.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from app.fsm.states import EditFree
from app.assistants.client import run_thread_safe, run_thread_safe_async
from app.edit.apply_intent import apply_intent
from app.formatters import report
from app.matcher import match_positions
from app.data_loader import load_products
from app.keyboards import build_main_kb
from app.converters import parsed_to_dict

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
    
    # Отправляем индикатор обработки
    processing_msg = await message.answer("🔄 Обрабатываю запрос...")
    
    try:
        logger.info("[edit_flow] Отправка текста пользователя в OpenAI", extra={"data": {"user_text": user_text}})
        # Используем асинхронную версию для лучшей производительности
        intent = await run_thread_safe_async(user_text)
        logger.info("[edit_flow] Ответ OpenAI получен", extra={"data": {"intent": intent}})
        
        # Проверяем успешность разбора
        if intent.get("action") == "unknown":
            error = intent.get("error", "unknown_error")
            logger.warning("[edit_flow] Не удалось разобрать команду", extra={"data": {"error": error}})
            
            # Удаляем сообщение о загрузке
            try:
                await processing_msg.delete()
            except Exception:
                pass
            
            # Используем пользовательское сообщение об ошибке, если оно есть
            error_message = intent.get("user_message", 
                "Не понял, что нужно изменить. Попробуйте переформулировать, например:\n"
                "• дата 16 апреля\n"
                "• строка 2 цена 95000"
            )
            
            await message.answer(error_message)
            return
            
        # Приведение invoice к dict через универсальный адаптер
        from app.converters import parsed_to_dict
        invoice = parsed_to_dict(invoice)
        
        # Применяем интент к инвойсу
        new_invoice = apply_intent(invoice, intent)
        
        # Пересчитываем ошибки и обновляем отчёт
        match_results = match_positions(new_invoice["positions"], load_products())
        text, has_errors = report.build_report(new_invoice, match_results)
    
        # Fuzzy-подсказка для некорректного имени позиции
        from rapidfuzz import process as fuzzy_process
        products = load_products()
        product_names = [p.name for p in products]
        
        # Флаг, который показывает, было ли изменение
        was_changed = True
        
        # Проверяем есть ли какие-то неизвестные позиции
        for idx, item in enumerate(match_results):
            if item.get("status") == "unknown":
                name_to_check = item.get("name", "")
                # Ищем ближайшее совпадение
                result = fuzzy_process.extractOne(name_to_check, product_names, score_cutoff=82)
                if result:
                    suggestion, score = result[0], result[1]
                    # Сохраняем оригинал и подсказку в state для дальнейшей логики
                    await state.update_data(
                        fuzzy_original=name_to_check, 
                        fuzzy_match=suggestion,
                        fuzzy_line=idx
                    )
                    
                    # Удаляем сообщение о загрузке
                    try:
                        await processing_msg.delete()
                    except Exception:
                        pass
                    
                    # Отправляем подсказку пользователю с кнопками
                    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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
                    
                    await message.answer(
                        f"Наверное, вы имели в виду <b>{suggestion}</b>?",
                        parse_mode="HTML",
                        reply_markup=keyboard
                    )
                    break  # Показываем только одну подсказку за раз
    
        # Подсчитываем количество оставшихся проблем
        issues_count = sum(1 for item in match_results if item.get("status", "") != "ok")
    
        # Обновляем данные в состоянии
        await state.update_data(invoice=new_invoice, issues_count=issues_count)
    
        # Генерируем клавиатуру в зависимости от наличия ошибок
        keyboard = build_main_kb(has_errors)
    
        # Удаляем сообщение о загрузке
        try:
            await processing_msg.delete()
        except Exception:
            pass
            
        # Отправляем обновлённый отчёт
        await message.answer(
            text, 
            reply_markup=keyboard, 
            parse_mode="HTML"
        )
    
        # Добавляем сообщение об успешном редактировании
        if was_changed:
            action_name = {
                "set_date": "дата",
                "set_price": "цена",
                "set_name": "название",
                "set_quantity": "количество",
                "set_unit": "единица измерения",
                "add_line": "новая позиция"
            }.get(intent.get("action", ""), "значение")
            
            success_message = f"✅ {action_name.capitalize()} успешно изменена!"
            if not has_errors:
                success_message += " Вы можете подтвердить инвойс."
                
            await message.answer(success_message)
    
        # Остаёмся в том же состоянии для продолжения редактирования
        await state.set_state(EditFree.awaiting_input)
        
    except Exception as e:
        logger.error("[edit_flow] Критическая ошибка при обработке команды", extra={"data": {"error": str(e)}})
        
        # Удаляем сообщение о загрузке
        try:
            await processing_msg.delete()
        except Exception:
            pass
            
        await message.answer(
            "Сервис временно недоступен. Пожалуйста, попробуйте позже.\n"
            "Если проблема повторяется, обратитесь к администратору."
        )
        # Не очищаем состояние, чтобы пользователь мог попробовать еще раз

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

# Обработчик подтверждения fuzzy-совпадения
@router.callback_query(F.data.startswith("fuzzy:confirm:"))
async def confirm_fuzzy_name(call: CallbackQuery, state: FSMContext):
    """
    Обработчик подтверждения fuzzy-совпадения названия позиции.
    
    Args:
        call: Объект callback запроса от нажатия кнопки "Да"
        state: FSM-контекст
    """
    # Получаем индекс строки из callback data
    line_idx = int(call.data.split(":")[-1])
    
    # Получаем данные из state
    data = await state.get_data()
    fuzzy_match = data.get("fuzzy_match")  # Предложенное название
    fuzzy_original = data.get("fuzzy_original")  # Оригинальное название
    invoice = data.get("invoice")
    
    if not all([fuzzy_match, invoice]):
        await call.message.answer("Ошибка: данные для подтверждения не найдены.")
        await call.message.edit_reply_markup(reply_markup=None)
        await call.answer()
        return
    
    # Отправляем индикатор обработки
    processing_msg = await call.message.answer("🔄 Применяю изменение...")
    
    try:
        # Обновляем название позиции
        invoice = parsed_to_dict(invoice)
        if 0 <= line_idx < len(invoice.get("positions", [])):
            # Изменяем название на предложенное
            invoice["positions"][line_idx]["name"] = fuzzy_match
            
            # Пересчитываем ошибки и обновляем отчёт
            match_results = match_positions(invoice["positions"], load_products())
            text, has_errors = report.build_report(invoice, match_results)
            
            # Добавляем алиас если строка успешно распознана
            product_id = None
            for pos in match_results:
                if pos.get("name") == fuzzy_match and pos.get("product_id"):
                    product_id = pos.get("product_id")
                    break
                    
            if product_id and fuzzy_original:
                from app.alias import add_alias
                add_alias(fuzzy_original, product_id)
                logger.info(f"[confirm_fuzzy_name] Added alias: {fuzzy_original} -> {product_id}")
            
            # Подсчитываем количество оставшихся проблем
            issues_count = sum(1 for item in match_results if item.get("status", "") != "ok")
            
            # Обновляем данные в состоянии
            await state.update_data(invoice=invoice, issues_count=issues_count)
            
            # Удаляем индикатор обработки
            try:
                await processing_msg.delete()
            except Exception:
                pass
                
            # Убираем кнопки с подсказкой
            await call.message.edit_reply_markup(reply_markup=None)
            
            # Генерируем клавиатуру в зависимости от наличия ошибок
            keyboard = build_main_kb(has_errors)
            
            # Отправляем обновлённый отчёт
            await call.message.answer(
                text, 
                reply_markup=keyboard, 
                parse_mode="HTML"
            )
            
            # Добавляем сообщение об успешном редактировании
            success_message = f"✅ Название позиции изменено на <b>{fuzzy_match}</b>!"
            if not has_errors:
                success_message += " Вы можете подтвердить инвойс."
                
            await call.message.answer(success_message, parse_mode="HTML")
        else:
            await call.message.answer(f"Ошибка: позиция с индексом {line_idx} не найдена.")
    
    except Exception as e:
        logger.error("[confirm_fuzzy_name] Ошибка при обновлении названия", extra={"data": {"error": str(e)}})
        
        # Удаляем индикатор обработки
        try:
            await processing_msg.delete()
        except Exception:
            pass
            
        await call.message.answer("Произошла ошибка при обновлении названия. Пожалуйста, попробуйте еще раз.")
    
    # Отвечаем на callback
    await call.answer()
    
    # Остаёмся в том же состоянии для продолжения редактирования
    await state.set_state(EditFree.awaiting_input)

# Обработчик отклонения fuzzy-совпадения
@router.callback_query(F.data.startswith("fuzzy:reject:"))
async def reject_fuzzy_name(call: CallbackQuery, state: FSMContext):
    """
    Обработчик отклонения fuzzy-совпадения названия позиции.
    
    Args:
        call: Объект callback запроса от нажатия кнопки "Нет"
        state: FSM-контекст
    """
    # Получаем индекс строки из callback data
    line_idx = int(call.data.split(":")[-1])
    
    # Получаем данные из state
    data = await state.get_data()
    fuzzy_original = data.get("fuzzy_original")
    
    # Убираем кнопки с подсказкой
    await call.message.edit_reply_markup(reply_markup=None)
    
    # Отправляем сообщение о необходимости ручного редактирования
    await call.message.answer(
        f"Хорошо, вы можете вручную отредактировать название, отправив команду:\n\n"
        f"<i>строка {line_idx+1} название [новое название]</i>",
        parse_mode="HTML"
    )
    
    # Отвечаем на callback
    await call.answer()
    
    # Остаёмся в том же состоянии для продолжения редактирования
    await state.set_state(EditFree.awaiting_input)