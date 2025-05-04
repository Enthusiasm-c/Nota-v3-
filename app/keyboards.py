from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

# Главное меню (inline)


def kb_main(lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Upload new invoice", callback_data="action:new"
                )
            ],
            [InlineKeyboardButton(text="ℹ️ Help", callback_data="action:help")],
        ]
    )


# Клавиатура для загрузки файла (reply)


def kb_upload() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="/cancel")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# Клавиатура помощи (reply)


def kb_help_back() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Back")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# Клавиатура отчёта (inline)


def kb_report(match_results: list) -> InlineKeyboardMarkup:
    # СТАРАЯ версия для совместимости
    edit_buttons = [
        [InlineKeyboardButton(text=f"✏️ Edit line {i+1}", callback_data=f"edit:{i}")]
        for i, r in enumerate(match_results)
        if r.get("status") != "ok"
    ]
    base_buttons = [
        [InlineKeyboardButton(text="✅ Confirm", callback_data="confirm:invoice")],
        *edit_buttons,
        [InlineKeyboardButton(text="🚫 Cancel", callback_data="cancel:all")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=base_buttons)


# --- D-2: UX финального отчёта ---


def build_invoice_report(
    text: str,
    has_errors: bool,
    match_results: list,
    page: int = 1,
    total_pages: int = 1,
    page_size: int = 15,
) -> InlineKeyboardMarkup:
    """
    Клавиатура финального отчёта:
    [✏️ Ред.n] ... (только строки текущей страницы)
    [➕ Add missing]
    [↩ Back] [✅ Submit] (Submit только если нет ошибок)
    Навигация: ◀ 1/3 ▶
    """
    # Определяем индексы строк текущей страницы
    start = (page - 1) * page_size
    end = start + page_size
    current_rows = match_results[start:end]
    # Кнопки редактирования только для строк с ошибками на текущей странице
    edit_buttons = [
        InlineKeyboardButton(text=f"✏️ Ред.{start + i + 1}", callback_data=f"edit:{start + i}")
        for i, r in enumerate(current_rows)
        if r.get("status") in ("unit_mismatch", "unknown")
    ]
    # Кнопка Add missing (только если есть нераспознанные)
    unknown_count = sum(1 for r in match_results if r.get("status") == "unknown")
    add_missing_btn = None
    if unknown_count > 0:
        add_missing_btn = InlineKeyboardButton(
            text="➕ Add missing", callback_data="inv_add_missing"
        )
    # Кнопка Back
    back_btn = InlineKeyboardButton(text="↩ Back", callback_data="inv_cancel_edit")
    # Кнопка Submit (только если нет ошибок)
    submit_btn = None
    if not has_errors:
        submit_btn = InlineKeyboardButton(text="✅ Submit", callback_data="inv_submit")
    # Пагинация
    nav_buttons = []
    if total_pages > 1:
        if page > 1:
            nav_buttons.append(
                InlineKeyboardButton(text="◀", callback_data=f"page_{page-1}")
            )
        nav_buttons.append(
            InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop")
        )
        if page < total_pages:
            nav_buttons.append(
                InlineKeyboardButton(text="▶", callback_data=f"page_{page+1}")
            )
    # Сборка клавиатуры
    keyboard = []
    for i in range(0, len(edit_buttons), 3):
        keyboard.append(edit_buttons[i : i + 3])
    if nav_buttons:
        keyboard.append(nav_buttons)
    if add_missing_btn:
        keyboard.append([add_missing_btn])
    btn_row = [back_btn]
    # Кнопка 'Подтвердить' только если нет ошибок
    if submit_btn and not has_errors:
        btn_row.append(submit_btn)
    keyboard.append(btn_row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
    # NB: Если есть ошибки — только кнопка 'Отмена' и кнопки редактирования


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
                InlineKeyboardButton(
                    text="Price", callback_data=f"field:price{suffix}"
                ),
            ],
            [InlineKeyboardButton(text="Cancel", callback_data=f"cancel{suffix}")],
        ]
    )


# Оставляем для совместимости (по одной строке)


def kb_edit(idx: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Edit", callback_data=f"edit:{idx}")]
        ]
    )


def kb_edit_fields(idx: int) -> InlineKeyboardMarkup:
    return kb_field_menu(idx)


# Кнопка Set supplier (inline)


def kb_set_supplier() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Set supplier", callback_data="set_supplier")]
        ]
    )


# Авто-кнопки unit (inline)


def kb_unit_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=unit, callback_data=f"unit:{unit}")
                for unit in ["kg", "g", "l", "ml", "pcs"]
            ]
        ]
    )


def kb_cancel_all() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚫 Cancel", callback_data="cancel:all")]
        ]
    )
