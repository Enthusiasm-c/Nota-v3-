import pytest
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from unittest.mock import AsyncMock, patch, MagicMock
from app.keyboards import build_main_kb
from app.fsm.states import EditFree


def test_keyboard_two_buttons_with_errors():
    """Тест: при наличии ошибок клавиатура содержит 2 кнопки (Редактировать, Отмена)"""
    kb = build_main_kb(has_errors=True)
    
    # Проверяем, что это InlineKeyboardMarkup
    assert isinstance(kb, InlineKeyboardMarkup)
    
    # Проверяем, что есть только одна строка кнопок
    assert len(kb.inline_keyboard) == 1
    
    # Проверяем, что в первой строке 2 кнопки
    assert len(kb.inline_keyboard[0]) == 2
    
    # Проверяем текст и callback_data кнопок
    assert kb.inline_keyboard[0][0].text == "✏️ Редактировать"
    assert kb.inline_keyboard[0][0].callback_data == "edit:free"
    
    assert kb.inline_keyboard[0][1].text == "↩ Отмена"
    assert kb.inline_keyboard[0][1].callback_data == "cancel:all"


def test_keyboard_three_buttons_no_errors():
    """Тест: при отсутствии ошибок клавиатура содержит 3 кнопки (Редактировать, Отмена, Подтвердить)"""
    kb = build_main_kb(has_errors=False)
    
    # Проверяем, что это InlineKeyboardMarkup
    assert isinstance(kb, InlineKeyboardMarkup)
    
    # Проверяем, что есть две строки кнопок
    assert len(kb.inline_keyboard) == 2
    
    # Проверяем, что в первой строке 2 кнопки
    assert len(kb.inline_keyboard[0]) == 2
    
    # Проверяем, что во второй строке 1 кнопка
    assert len(kb.inline_keyboard[1]) == 1
    
    # Проверяем текст и callback_data кнопок
    assert kb.inline_keyboard[0][0].text == "✏️ Редактировать"
    assert kb.inline_keyboard[0][0].callback_data == "edit:free"
    
    assert kb.inline_keyboard[0][1].text == "↩ Отмена"
    assert kb.inline_keyboard[0][1].callback_data == "cancel:all"
    
    assert kb.inline_keyboard[1][0].text == "✅ Подтвердить"
    assert kb.inline_keyboard[1][0].callback_data == "confirm:invoice"


def test_build_edit_keyboard_forwards_to_build_main_kb():
    """Тест: функция build_edit_keyboard должна вызывать build_main_kb"""
    from app.keyboards import build_edit_keyboard
    
    # Проверяем для случая с ошибками
    kb1 = build_edit_keyboard(has_errors=True)
    kb2 = build_main_kb(has_errors=True)
    
    # Сравниваем структуру клавиатур
    assert len(kb1.inline_keyboard) == len(kb2.inline_keyboard)
    
    # Проверяем для случая без ошибок
    kb1 = build_edit_keyboard(has_errors=False)
    kb2 = build_main_kb(has_errors=False)
    
    # Сравниваем структуру клавиатур
    assert len(kb1.inline_keyboard) == len(kb2.inline_keyboard)


@pytest.mark.asyncio
async def test_cb_edit_line_state_transition():
    """Тест: cb_edit_line переводит состояние в EditFree.awaiting_input"""
    import bot
    
    # Создаем моки
    callback = AsyncMock()
    callback.from_user = MagicMock(id=123)
    callback.message = AsyncMock()
    callback.message.message_id = 456
    callback.data = "edit:free"
    
    state = AsyncMock()
    
    # Вызываем функцию
    await bot.cb_edit_line(callback, state)
    
    # Проверяем, что состояние было установлено в EditFree.awaiting_input
    state.set_state.assert_awaited_with(EditFree.awaiting_input)
    
    # Проверяем, что был вызван answer
    callback.answer.assert_awaited()
    
    # Проверяем, что был вызван message.answer с инструкцией
    callback.message.answer.assert_awaited()
    
    # Проверяем, что в state сохранен message_id
    state.update_data.assert_awaited_with(edit_msg_id=456)