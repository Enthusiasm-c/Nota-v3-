from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# Главное меню (inline)
def kb_main(lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Upload new invoice", callback_data="action:new")],
            [InlineKeyboardButton(text="ℹ️ Help", callback_data="action:help")],
        ]
    )

# Клавиатура для загрузки файла (reply)
def kb_upload() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="/cancel")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

# Клавиатура помощи (reply)
def kb_help_back() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Back")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

# Клавиатура отчёта (inline)
def kb_report(match_results: list) -> InlineKeyboardMarkup:
    # Кнопки Edit только для проблемных строк
    edit_buttons = [
        [InlineKeyboardButton(text=f"✏️ Edit line {i+1}", callback_data=f"edit:{i}")]
        for i, r in enumerate(match_results) if r.get("status") != "ok"
    ]
    # Confirm + Cancel всегда
    base_buttons = [
        [InlineKeyboardButton(text="✅ Confirm", callback_data="confirm:invoice")],
        *edit_buttons,
        [InlineKeyboardButton(text="🚫 Cancel", callback_data="cancel:all")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=base_buttons)

# Меню выбора поля для редактирования (inline)
def kb_field_menu(idx: int = None) -> InlineKeyboardMarkup:
    # Универсальный вариант: если idx=None, то просто field:name и т.д.
    suffix = f":{idx}" if idx is not None else ""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Name", callback_data=f"field:name{suffix}"),
                InlineKeyboardButton(text="Qty", callback_data=f"field:qty{suffix}"),
                InlineKeyboardButton(text="Unit", callback_data=f"field:unit{suffix}"),
                InlineKeyboardButton(text="Price", callback_data=f"field:price{suffix}")
            ],
            [InlineKeyboardButton(text="Cancel", callback_data=f"cancel{suffix}")]
        ]
    )

# Оставляем для совместимости (по одной строке)
def kb_edit(idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✏️ Edit", callback_data=f"edit:{idx}")]]
    )

def kb_edit_fields(idx: int) -> InlineKeyboardMarkup:
    return kb_field_menu(idx)

# Кнопка Set supplier (inline)
def kb_set_supplier() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✏️ Set supplier", callback_data="set_supplier")]]
    )

# Авто-кнопки unit (inline)
def kb_unit_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=unit, callback_data=f"unit:{unit}") for unit in ["kg", "g", "l", "ml", "pcs"]]
        ]
    )

def kb_cancel_all() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🚫 Cancel", callback_data="cancel:all")]]
    )
