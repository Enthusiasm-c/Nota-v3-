import logging

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from app.i18n import t

logger = logging.getLogger(__name__)


def kb_main(lang: str = "en") -> InlineKeyboardMarkup:
    """
    Создает клавиатуру главного меню.

    Args:
        lang: Код языка для интернационализации

    Returns:
        InlineKeyboardMarkup с кнопками главного меню
    """
    logger.debug(f"Creating main menu keyboard with lang={lang}")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📷 " + t("buttons.new_photo", {"default": "Новое фото"}, lang),
                    callback_data="action:new",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❓ " + t("buttons.help", {"default": "Помощь"}, lang),
                    callback_data="action:help",
                )
            ],
        ]
    )

    return keyboard


def kb_upload(lang: str = "en") -> ReplyKeyboardMarkup:
    """
    Создает клавиатуру для режима загрузки фото.

    Args:
        lang: Код языка для интернационализации

    Returns:
        ReplyKeyboardMarkup с кнопкой отмены
    """
    logger.debug(f"Creating upload keyboard with lang={lang}")

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ " + t("buttons.cancel", {"default": "Отмена"}, lang))]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    return keyboard


def kb_help_back(lang: str = "en") -> ReplyKeyboardMarkup:
    """
    Создает клавиатуру для экрана помощи с кнопкой "Назад".

    Args:
        lang: Код языка для интернационализации

    Returns:
        ReplyKeyboardMarkup с кнопкой "Назад"
    """
    logger.debug(f"Creating help-back keyboard with lang={lang}")

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="◀️ " + t("buttons.back", {"default": "Назад"}, lang))]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    return keyboard


def kb_set_supplier(lang: str = "en") -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с кнопкой установки поставщика.

    Args:
        lang: Код языка для интернационализации

    Returns:
        InlineKeyboardMarkup с кнопкой установки поставщика
    """
    logger.debug(f"Creating set-supplier keyboard with lang={lang}")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏢 " + t("buttons.set_supplier", {"default": "Указать поставщика"}, lang),
                    callback_data="set_supplier",
                )
            ]
        ]
    )

    return keyboard


def kb_unit_buttons() -> InlineKeyboardMarkup:
    """
    Создает клавиатуру с кнопками единиц измерения.

    Returns:
        InlineKeyboardMarkup с кнопками единиц измерения
    """
    logger.debug("Creating unit buttons keyboard")

    # Добавляем эмодзи для улучшения восприятия
    unit_map = {
        "kg": "⚖️ kg",  # весы
        "g": "🧂 g",  # щепотка
        "l": "🥛 l",  # стакан
        "ml": "💧 ml",  # капля
        "pcs": "🔢 pcs",  # числа
    }

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=unit_map.get(unit, unit), callback_data=f"unit:{unit}")
                for unit in ["kg", "g"]
            ],
            [
                InlineKeyboardButton(text=unit_map.get(unit, unit), callback_data=f"unit:{unit}")
                for unit in ["l", "ml", "pcs"]
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel:all")],
        ]
    )

    return keyboard


def kb_cancel_all(lang: str = "en") -> InlineKeyboardMarkup:
    """
    Создает клавиатуру только с кнопкой отмены.

    Args:
        lang: Код языка для интернационализации

    Returns:
        InlineKeyboardMarkup с кнопкой отмены
    """
    logger.debug(f"Creating cancel-all keyboard with lang={lang}")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="❌ " + t("buttons.cancel", {"default": "Отмена"}, lang),
                    callback_data="cancel:all",
                )
            ]
        ]
    )

    return keyboard


def build_main_kb(has_errors: bool = True, lang: str = "en") -> InlineKeyboardMarkup:
    """
    Создает упрощенную клавиатуру для отчета - только кнопка подтверждения при отсутствии ошибок.
    Редактирование и отмена доступны через текстовые команды.

    Args:
        has_errors: Флаг, указывающий есть ли ошибки в отчете
        lang: Код языка для интернационализации

    Returns:
        InlineKeyboardMarkup с кнопкой подтверждения (если нет ошибок) или пустая клавиатура
    """
    logger.debug(f"Creating simplified keyboard with has_errors={has_errors}, lang={lang}")

    # Если есть ошибки - показываем пустую клавиатуру (пользователь может сразу писать команды)
    if has_errors:
        return InlineKeyboardMarkup(inline_keyboard=[])

    # Если ошибок нет - показываем только кнопку подтверждения для безопасности
    confirm_button = InlineKeyboardButton(
        text="✅ " + t("buttons.confirm", {"default": "Подтвердить"}, lang),
        callback_data="confirm:invoice",
    )

    return InlineKeyboardMarkup(inline_keyboard=[[confirm_button]])


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
                    callback_data="edit_field:name",
                ),
                InlineKeyboardButton(
                    text="🔢 " + t("buttons.edit_qty", {"default": "Количество"}, lang),
                    callback_data="edit_field:qty",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⚖️ " + t("buttons.edit_unit", {"default": "Ед. изм."}, lang),
                    callback_data="edit_field:unit",
                ),
                InlineKeyboardButton(
                    text="💰 " + t("buttons.edit_price", {"default": "Цена"}, lang),
                    callback_data="edit_field:price",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ " + t("buttons.cancel", {"default": "Отмена"}, lang),
                    callback_data="cancel:all",
                )
            ],
        ]
    )

    return keyboard
