from decimal import Decimal, InvalidOperation
from typing import Any, Union

# Ширины колонок для табличного отчёта
W_IDX = 3
W_NAME = 22
W_QTY = 6
W_UNIT = 6
W_PRICE = 10
W_TOTAL = 11
W_STATUS = 12


def escape_md(text: str, version: int = 2) -> str:
    # Escapes all special characters for MarkdownV2
    # https://core.telegram.org/bots/api#markdownv2-style
    if not isinstance(text, str):
        text = str(text)
    specials = r"_*[]()~`>#+-=|{}.!"
    for c in specials:
        text = text.replace(c, f"\\{c}")
    return text


def format_idr(val: Any) -> str:
    """Форматирует число в стиль '1 234 567 IDR' с узким пробелом"""
    try:
        if val is None:
            return "—"
        dec = Decimal(str(val))
        return f"{dec:,.0f}".replace(",", "\u2009") + " IDR"
    except (InvalidOperation, ValueError, TypeError):
        return "—"


def _row(
    idx: Union[str, int],
    name: str,
    qty: Union[str, int, float],
    unit: str,
    price: Any,
    total: Any,
    status: Union[str, None],
) -> str:
    name = (name[: W_NAME - 1] + "…") if len(name) > W_NAME else name
    price_str = format_idr(price) if price not in (None, "") else "—"
    total_str = format_idr(total) if total not in (None, "") else "—"
    status_str = status if status else ""
    return (
        f"{str(idx).ljust(W_IDX)}"
        f"{name.ljust(W_NAME)}"
        f"{str(qty).rjust(W_QTY)} "
        f"{unit.ljust(W_UNIT)} "
        f"{price_str.rjust(W_PRICE)} "
        f"{total_str.rjust(W_TOTAL)} "
        f"{status_str}"
    )


# build_table удалён — используйте app/formatters/report.py


# build_report и build_table удалены — используйте app/formatters/report.py
