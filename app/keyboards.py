from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from typing import Optional



def kb_edit(idx: int) -> InlineKeyboardMarkup:
    """Single Edit button for a problem row."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✏️ Edit", callback_data=f"edit:{idx}")]]
    )


def kb_choose_field(idx: int) -> InlineKeyboardMarkup:
    """2x3 grid: Name, Qty, Unit (row 1), Price, Cancel (row 2)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Name", callback_data=f"field:name:{idx}"),
                InlineKeyboardButton(text="Qty", callback_data=f"field:qty:{idx}"),
                InlineKeyboardButton(text="Unit", callback_data=f"field:unit:{idx}")
            ],
            [
                InlineKeyboardButton(text="Price", callback_data=f"field:price:{idx}"),
                InlineKeyboardButton(text="Cancel", callback_data=f"cancel:{idx}")
            ]
        ]
    )


def kb_cancel_all() -> InlineKeyboardMarkup:
    """Global cancel button under the report."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🚫 Cancel edit", callback_data="cancel:all")]]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)

def build_invoice_report(positions):
    # Simple Markdown summary for demo
    lines = []
    for pos in positions:
        if pos.get("status") == "removed":
            continue
        status = pos.get("status", "unknown")
        emoji = "✅" if status == "ok" else ("⚠️" if status == "unknown" else "✏️")
        lines.append(f"{emoji} {pos['name']} {pos['qty']} {pos['unit']}")
    return "\n".join(lines)
