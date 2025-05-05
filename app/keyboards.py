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


# Клавиатура редактирования (inline)




# Клавиатура отчёта (inline)



# --- D-2: UX финального отчёта ---


# Устаревшая функция, заменена на build_main_kb
# def build_invoice_report(
#     text: str,
#     has_errors: bool,
#     match_results: list,
#     page: int = 1,
#     total_pages: int = 1,
#     page_size: int = 15,
# ) -> InlineKeyboardMarkup:
#     """
#     Клавиатура финального отчёта:
#     [✏️ Ред.n] ... (только строки текущей страницы)
#     [➕ Add missing]
#     [↩ Back] [✅ Submit] (Submit только если нет ошибок)
#     Навигация: ◀ 1/3 ▶
#     """
#     # Определяем индексы строк текущей страницы
#     start = (page - 1) * page_size
#     end = start + page_size
#     current_rows = match_results[start:end]
#     # Кнопки редактирования только для строк с ошибками на текущей странице
#     edit_buttons = [
#         InlineKeyboardButton(text=f"✏️ Ред.{start + i + 1}", callback_data=f"edit:{start + i}")
#         for i, r in enumerate(current_rows)
#         if r.get("status") in ("unit_mismatch", "unknown")
#     ]
#     # Кнопка Add missing (только если есть нераспознанные)
#     unknown_count = sum(1 for r in match_results if r.get("status") == "unknown")
#     add_missing_btn = None
#     if unknown_count > 0:
#         add_missing_btn = InlineKeyboardButton(
#             text="➕ Add missing", callback_data="inv_add_missing"
#         )
#     # Кнопка Back
#     back_btn = InlineKeyboardButton(text="↩ Back", callback_data="inv_cancel_edit")
#     # Кнопка Submit (только если нет ошибок)
#     submit_btn = None
#     if not has_errors:
#         submit_btn = InlineKeyboardButton(text="✅ Submit", callback_data="inv_submit")
#     # Если есть ошибки, submit_btn остается None и не добавляется в клавиатуру
#     # Пагинация
#     nav_buttons = []


# Меню выбора поля для редактирования (inline)





# Оставляем для совместимости (по одной строке)








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


def build_main_kb(has_errors: bool = True) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для редактирования отчета с 2-3 основными кнопками.
    
    Args:
        has_errors: Флаг наличия ошибок в отчете
        
    Returns:
        InlineKeyboardMarkup с кнопками:
        - "✏ Редактировать" - всегда присутствует
        - "↩ Отмена" - всегда присутствует
        - "✅ Подтвердить" - только если нет ошибок (has_errors=False)
    """
    keyboard_rows = [
        [
            InlineKeyboardButton(
                text="✏️ Редактировать", callback_data="edit:free"
            ),
            InlineKeyboardButton(
                text="↩ Отмена", callback_data="cancel:all"
            )
        ]
    ]
    
    # Добавляем кнопку подтверждения только если нет ошибок
    if not has_errors:
        keyboard_rows.append([
            InlineKeyboardButton(
                text="✅ Подтвердить", callback_data="confirm:invoice"
            )
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


# Функция для обратной совместимости, заменяем на build_main_kb
def build_edit_keyboard(has_errors: bool = True) -> InlineKeyboardMarkup:
    """
    Устаревшая функция для обратной совместимости.
    Использует новый build_main_kb.
    
    Args:
        has_errors: Флаг наличия ошибок в отчете
        
    Returns:
        InlineKeyboardMarkup с новыми кнопками
    """
    return build_main_kb(has_errors)
