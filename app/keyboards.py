from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from app.i18n import t
import logging

logger = logging.getLogger(__name__)

def kb_main(lang: str = "en") -> InlineKeyboardMarkup:
    """
    Creates main menu keyboard.
    
    Args:
        lang: Language code for internationalization
        
    Returns:
        InlineKeyboardMarkup with main menu buttons
    """
    logger.debug(f"Creating main menu keyboard with lang={lang}")
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("buttons.new_photo", {"default": "New Photo"}, lang), 
                    callback_data="action:new"
                )
            ],
            [
                InlineKeyboardButton(
                    text=t("buttons.help", {"default": "Help"}, lang), 
                    callback_data="action:help"
                )
            ]
        ]
    )
    
    return keyboard


def kb_upload(lang: str = "en") -> ReplyKeyboardMarkup:
    """
    Creates keyboard for photo upload mode.
    
    Args:
        lang: Language code for internationalization
        
    Returns:
        ReplyKeyboardMarkup with cancel button
    """
    logger.debug(f"Creating upload keyboard with lang={lang}")
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t("buttons.cancel", {"default": "Cancel"}, lang))]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    
    return keyboard


def kb_help_back(lang: str = "en") -> ReplyKeyboardMarkup:
    """
    Creates keyboard for help screen with "Back" button.
    
    Args:
        lang: Language code for internationalization
        
    Returns:
        ReplyKeyboardMarkup with "Back" button
    """
    logger.debug(f"Creating help-back keyboard with lang={lang}")
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t("buttons.back", {"default": "Back"}, lang))]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    
    return keyboard


def kb_set_supplier(lang: str = "en") -> InlineKeyboardMarkup:
    """
    Creates keyboard with supplier setting button.
    
    Args:
        lang: Language code for internationalization
        
    Returns:
        InlineKeyboardMarkup with supplier setting button
    """
    logger.debug(f"Creating set-supplier keyboard with lang={lang}")
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("buttons.set_supplier", {"default": "Set Supplier"}, lang), 
                    callback_data="set_supplier"
                )
            ]
        ]
    )
    
    return keyboard


def kb_unit_buttons() -> InlineKeyboardMarkup:
    """
    Creates keyboard with unit buttons.
    
    Returns:
        InlineKeyboardMarkup with unit buttons
    """
    logger.debug("Creating unit buttons keyboard")
    
    unit_map = {
        "kg": "kg",
        "g": "g",
        "l": "l",
        "ml": "ml",
        "pcs": "pcs"
    }
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=unit_map.get(unit, unit), 
                    callback_data=f"unit:{unit}"
                ) 
                for unit in ["kg", "g"]
            ],
            [
                InlineKeyboardButton(
                    text=unit_map.get(unit, unit), 
                    callback_data=f"unit:{unit}"
                )
                for unit in ["l", "ml", "pcs"]
            ],
            [
                InlineKeyboardButton(
                    text="Cancel", 
                    callback_data="cancel:all"
                )
            ]
        ]
    )
    
    return keyboard


def kb_cancel_all(lang: str = "en") -> InlineKeyboardMarkup:
    """
    Creates keyboard with only cancel button.
    
    Args:
        lang: Language code for internationalization
        
    Returns:
        InlineKeyboardMarkup with cancel button
    """
    logger.debug(f"Creating cancel-all keyboard with lang={lang}")
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=t("buttons.cancel", {"default": "Cancel"}, lang), 
                    callback_data="cancel:all"
                )
            ]
        ]
    )
    
    return keyboard


def build_main_kb(has_errors: bool = True, lang: str = "en") -> InlineKeyboardMarkup:
    """
    Creates keyboard for report editing.
    
    Args:
        has_errors: Flag indicating if there are errors in the report
        lang: Language code for internationalization
        
    Returns:
        InlineKeyboardMarkup with edit and confirm/cancel buttons
    """
    logger.debug(f"Creating main keyboard with has_errors={has_errors}, lang={lang}")
    
    buttons = []
    
    # Edit button with warning emoji if has errors
    buttons.append([
        InlineKeyboardButton(
            text=f"{'⚠️' if has_errors else '✏️'} {t('buttons.edit', {'default': 'Edit'}, lang)}",
            callback_data="edit:free"
        )
    ])
    
    # Confirm button (always show, but with warning if has errors)
    buttons.append([
        InlineKeyboardButton(
            text=f"{'⚠️' if has_errors else '✅'} {t('buttons.confirm', {'default': 'Confirm'}, lang)}",
            callback_data="confirm:invoice"
        )
    ])
    
    # Cancel button
    buttons.append([
        InlineKeyboardButton(
            text=f"❌ {t('buttons.cancel', {'default': 'Cancel'}, lang)}",
            callback_data="cancel:all"
        )
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_edit_keyboard(has_errors: bool = True, lang: str = "en") -> InlineKeyboardMarkup:
    """
    Функция для обратной совместимости.
    Использует новую функцию build_main_kb.
    
    Args:
        has_errors: Флаг, указывающий есть ли ошибки в отчете
        lang: Код языка для интернационализации
        
    Returns:
        InlineKeyboardMarkup от функции build_main_kb
    """
    logger.debug(f"Called legacy build_edit_keyboard with has_errors={has_errors}, lang={lang}")
    return build_main_kb(has_errors, lang)


def kb_edit_field(lang: str = "en") -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для выбора поля для редактирования.
    
    Args:
        lang: Код языка для интернационализации
        
    Returns:
        InlineKeyboardMarkup с кнопками редактирования полей и отмены
    """
    logger.debug(f"Creating edit-field keyboard with lang={lang}")
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 " + t("buttons.edit_name", {"default": "Название"}, lang), 
                    callback_data="edit_field:name"
                ),
                InlineKeyboardButton(
                    text="🔢 " + t("buttons.edit_qty", {"default": "Количество"}, lang), 
                    callback_data="edit_field:qty"
                )
            ],
            [
                InlineKeyboardButton(
                    text="⚖️ " + t("buttons.edit_unit", {"default": "Ед. изм."}, lang), 
                    callback_data="edit_field:unit"
                ),
                InlineKeyboardButton(
                    text="💰 " + t("buttons.edit_price", {"default": "Цена"}, lang), 
                    callback_data="edit_field:price"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ " + t("buttons.cancel", {"default": "Отмена"}, lang), 
                    callback_data="cancel:all"
                )
            ]
        ]
    )
    
    return keyboard