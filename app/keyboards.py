from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from typing import Optional



def build_position_kb(idx: int, status: str) -> Optional[InlineKeyboardMarkup]:
    # Only a single 'Edit' button for unknown/invalid rows
    if status == "ok":
        return None
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Edit", callback_data=f"edit:{idx}")]
    ])



def build_inline(position_id: int):
    # Only a single 'Edit' button for unknown/invalid rows
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Edit", callback_data=f"pos:{position_id}:edit")]
        ]
    )

def build_invoice_keyboard(positions):
    # Only a single 'Edit' button per unknown/invalid row
    rows = []
    for idx, pos in enumerate(positions):
        if pos.get("status") == "removed":
            continue
        rows.append([
            InlineKeyboardButton(
                text=f"{pos['name']} {pos['qty']} {pos['unit']}",
                callback_data=f"pos:{idx}:noop"
            )
        ])
        if pos.get("status") != "ok":
            rows.append([
                InlineKeyboardButton(text="✏️ Edit", callback_data=f"pos:{idx}:edit")
            ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_global_cancel_kb():
    """Returns an inline keyboard with a single global Cancel button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="global:cancel")]
        ]
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
