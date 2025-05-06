from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from app.i18n import t

# Main menu (inline)


def kb_main(lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("button.upload_new", lang), callback_data="action:new"
                )
            ],
            [InlineKeyboardButton(text=t("button.help", lang), callback_data="action:help")],
        ]
    )


# Upload file keyboard (reply)


def kb_upload(lang: str = "en") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="/cancel")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# Help back keyboard (reply)


def kb_help_back(lang: str = "en") -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("button.back", lang))]],
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








# Set supplier button (inline)


def kb_set_supplier(lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t("button.set_supplier", lang), callback_data="set_supplier")]
        ]
    )


# Auto-unit buttons (inline)


def kb_unit_buttons() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=unit, callback_data=f"unit:{unit}")
                for unit in ["kg", "g", "l", "ml", "pcs"]
            ]
        ]
    )


def kb_cancel_all(lang: str = "en") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚫 " + t("button.cancel", lang), callback_data="cancel:all")]
        ]
    )


def build_main_kb(has_errors: bool = True, lang: str = "en") -> InlineKeyboardMarkup:
    """
    Creates a keyboard for editing a report with 2-3 main buttons.
    
    Args:
        has_errors: Flag indicating if there are errors in the report
        lang: Language code for localization
        
    Returns:
        InlineKeyboardMarkup with buttons:
        - "✏ Edit" - always present
        - "↩ Cancel" - always present
        - "✅ Confirm" - only if there are no errors (has_errors=False)
    """
    keyboard_rows = [
        [
            InlineKeyboardButton(
                text=t("button.edit", lang), callback_data="edit:free"
            ),
            InlineKeyboardButton(
                text=t("button.cancel", lang), callback_data="cancel:all"
            )
        ]
    ]
    
    # Add confirmation button only if there are no errors
    if not has_errors:
        keyboard_rows.append([
            InlineKeyboardButton(
                text=t("button.confirm", lang), callback_data="confirm:invoice"
            )
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


# Function for backward compatibility, replaced with build_main_kb
def build_edit_keyboard(has_errors: bool = True, lang: str = "en") -> InlineKeyboardMarkup:
    """
    Deprecated function for backward compatibility.
    Uses the new build_main_kb.
    
    Args:
        has_errors: Flag indicating if there are errors in the report
        lang: Language code for localization
        
    Returns:
        InlineKeyboardMarkup with the new buttons
    """
    return build_main_kb(has_errors, lang)
