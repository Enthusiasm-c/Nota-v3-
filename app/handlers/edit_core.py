"""
Ядро системы редактирования для Nota-v3: общая логика обработки пользовательского ввода,
применения интентов и пересчёта отчёта для edit_flow и incremental_edit_flow.
"""

import logging
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from app.edit.apply_intent import apply_intent
from app.formatters import report
from app.matcher import match_positions
from app.data_loader import load_products
from app.converters import parsed_to_dict
from app.i18n import t

logger = logging.getLogger(__name__)

async def process_user_edit(
    message: Message,
    state: FSMContext,
    user_text: str,
    lang: str = "en",
    send_processing=None,
    send_result=None,
    send_error=None,
    run_openai_intent=None,
    fuzzy_suggester=None,
    edit_state=None
):
    """
    Универсальная функция обработки пользовательского ввода для редактирования инвойса.
    Аргументы:
        message: объект сообщения Telegram
        state: FSMContext
        user_text: текст пользователя
        lang: язык пользователя
        send_processing: функция для отображения процесса (опционально)
        send_result: функция для отправки результата (опционально)
        send_error: функция для отправки ошибки (опционально)
        run_openai_intent: функция для вызова OpenAI (опционально)
        fuzzy_suggester: функция для показа fuzzy-предложений (опционально)
        edit_state: функция для обновления состояния FSM (опционально)
    """
    # Проверка на отмену
    if user_text.lower() in ["cancel", "отмена"]:
        if send_result:
            await send_result(t("status.edit_cancelled", lang=lang))
        await state.set_state(None)
        return

    data = await state.get_data()
    invoice = data.get("invoice")
    if not invoice:
        if send_error:
            await send_error(t("status.session_expired", lang=lang))
        await state.clear()
        return

    if send_processing:
        await send_processing(t("status.processing", lang=lang))

    # Вызов OpenAI для получения интента
    try:
        if run_openai_intent:
            intent = await run_openai_intent(user_text)
        else:
            from app.assistants.client import run_thread_safe_async
            intent = await run_thread_safe_async(user_text)
    except Exception as e:
        logger.error(f"[edit_core] Ошибка OpenAI: {e}")
        if send_error:
            await send_error(t("error.openai_failed", lang=lang))
        return

    # Проверка на неизвестный интент
    if intent.get("action") == "unknown":
        error_message = intent.get("user_message", t("error.parse_command", lang=lang))
        if send_error:
            await send_error(error_message)
        return

    invoice = parsed_to_dict(invoice)
    new_invoice = apply_intent(invoice, intent)

    # Пересчёт совпадений
    products = load_products()
    match_results = match_positions(new_invoice["positions"], products)
    
    # Явно считаем ошибки для более надежного определения статуса
    unknown_count = sum(1 for r in match_results if r.get("status") == "unknown")
    partial_count = sum(1 for r in match_results if r.get("status") == "partial")
    
    # Логируем для отладки
    logger.info(f"Результаты редактирования: unknown={unknown_count}, partial={partial_count}")
    
    # Обновляем состояние с явными счетчиками ошибок
    await state.update_data(unknown_count=unknown_count, partial_count=partial_count)
    
    # Формируем отчет
    text, has_errors = report.build_report(new_invoice, match_results)
    
    # Если каким-то образом build_report решил, что ошибок нет, но у нас есть unknown/partial,
    # явно устанавливаем has_errors=True
    if not has_errors and (unknown_count > 0 or partial_count > 0):
        logger.warning(f"Принудительно устанавливаем has_errors=True, так как unknown={unknown_count}, partial={partial_count}")
        has_errors = True

    # Fuzzy-сопоставление
    suggestion_shown = False
    for idx, item in enumerate(match_results):
        if item.get("status") == "unknown" and fuzzy_suggester:
            name_to_check = item.get("name", "")
            suggestion_shown = await fuzzy_suggester(message, state, name_to_check, idx, lang)
            if suggestion_shown:
                await state.update_data(invoice=new_invoice)
                if edit_state:
                    await edit_state()
                return

    # Обновление состояния
    await state.update_data(invoice=new_invoice)
    if edit_state:
        await edit_state()

    # Отправка результата
    if send_result:
        await send_result(text)

    return new_invoice, match_results, has_errors
