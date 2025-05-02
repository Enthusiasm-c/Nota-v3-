from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from typing import Optional

def build_position_kb(idx: int, status: str) -> Optional[InlineKeyboardMarkup]:
    if status == "ok":
        return None
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Edit", callback_data=f"edit:{idx}")],
        [InlineKeyboardButton(text="✅ OK",  callback_data=f"ok:{idx}"),
         InlineKeyboardButton(text="🗑 Delete", callback_data=f"del:{idx}")]
    ])

def build_inline(position_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ OK", callback_data=f"pos:{position_id}:ok"),
                InlineKeyboardButton(text="✏️ Edit", callback_data=f"pos:{position_id}:edit"),
                InlineKeyboardButton(text="🗑 Remove", callback_data=f"pos:{position_id}:remove"),
            ]
        ]
    )

def build_invoice_keyboard(positions):
    # One block per position (not grouped, for simplicity)
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
        rows.append([
            InlineKeyboardButton(text="✅ OK", callback_data=f"pos:{idx}:ok"),
            InlineKeyboardButton(text="✏️ Edit", callback_data=f"pos:{idx}:edit"),
            InlineKeyboardButton(text="🗑 Remove", callback_data=f"pos:{idx}:remove"),
        ])
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
