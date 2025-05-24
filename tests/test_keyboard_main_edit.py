from aiogram.types import InlineKeyboardMarkup

from app.keyboards import build_main_kb


def test_keyboard_empty_with_errors():
    """Test: if there are errors, keyboard is empty (users can type commands directly)"""
    kb = build_main_kb(has_errors=True)

    # Проверяем, что это InlineKeyboardMarkup
    assert isinstance(kb, InlineKeyboardMarkup)

    # Проверяем, что клавиатура пустая
    assert len(kb.inline_keyboard) == 0


def test_keyboard_confirm_only_no_errors():
    """Test: if there are no errors, keyboard has only Confirm button"""
    kb = build_main_kb(has_errors=False)

    # Проверяем, что это InlineKeyboardMarkup
    assert isinstance(kb, InlineKeyboardMarkup)

    # Проверяем, что есть одна строка кнопок
    assert len(kb.inline_keyboard) == 1

    # Проверяем, что в строке одна кнопка
    assert len(kb.inline_keyboard[0]) == 1

    # Проверяем текст и callback_data кнопки
    assert kb.inline_keyboard[0][0].text == "✅ Confirm"
    assert kb.inline_keyboard[0][0].callback_data == "confirm:invoice"


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
