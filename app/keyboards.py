from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from typing import Optional



def kb_edit(idx: int) -> InlineKeyboardMarkup:
    """Single Edit button for a problem row."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✏️ Edit", callback_data=f"edit:{idx}")]]
    )


def kb_edit_fields(idx: int) -> InlineKeyboardMarkup:
    """First row: Name, Qty, Unit, Price; Second row: Cancel only."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Name", callback_data=f"field:name:{idx}"),
                InlineKeyboardButton(text="Qty", callback_data=f"field:qty:{idx}"),
                InlineKeyboardButton(text="Unit", callback_data=f"field:unit:{idx}"),
                InlineKeyboardButton(text="Price", callback_data=f"field:price:{idx}")
            ],
            [
                InlineKeyboardButton(text="Cancel", callback_data=f"cancel:{idx}")
            ]
        ]
    )


def kb_cancel_all() -> InlineKeyboardMarkup:
    """Global cancel button under the report."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🚫 Cancel edit", callback_data="cancel:all")]]
    )

# kb_edit remains as is (single Edit button)
# Remove any dead code after kb_cancel_all
