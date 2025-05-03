def escape_md(text, version=2):
    # Escapes all special characters for MarkdownV2
    # https://core.telegram.org/bots/api#markdownv2-style
    if not isinstance(text, str):
        text = str(text)
    specials = r"_*[]()~`>#+-=|{}.!"
    for c in specials:
        text = text.replace(c, f"\\{c}")
    return text

# Fixed column widths
W_IDX, W_NAME, W_QTY, W_UNIT, W_PRICE, W_STATUS = 3, 22, 6, 6, 9, 12

def _row(idx, name, qty, unit, price, status):
    name = (name[:W_NAME-1] + "…") if len(name) > W_NAME else name
    # Корректно форматируем price
    try:
        price_val = float(price)
        price_str = f"{price_val:,.0f}"
    except (TypeError, ValueError):
        price_str = "—"
    return (
        f"{str(idx).ljust(W_IDX)}"
        f"{name.ljust(W_NAME)}"
        f"{str(qty).rjust(W_QTY)} "
        f"{unit.ljust(W_UNIT)} "
        f"{price_str.rjust(W_PRICE)} "
        f"{status}"
    )

def build_table(rows: list[str]) -> str:
    header = _row("#", "NAME", "QTY", "UNIT", "PRICE", "STATUS")
    divider = "─" * len(header)
    body = "\n".join(rows)
    return f"```\n{header}\n{divider}\n{body}\n```"

def build_report(parsed_data, match_results: list) -> str:
    # Support both dict and ParsedData object
    supplier = getattr(parsed_data, "supplier", None)
    if supplier is None and isinstance(parsed_data, dict):
        supplier = parsed_data.get("supplier", None)
    date = getattr(parsed_data, "date", None)
    if date is None and isinstance(parsed_data, dict):
        date = parsed_data.get("date", None)
    supplier_str = "Unknown supplier" if not supplier else escape_md(str(supplier), version=2)
    date_str = "—" if not date else escape_md(str(date), version=2)
    ok_count = sum(1 for r in match_results if r.get("status") == "ok")
    unit_mismatch_count = sum(1 for r in match_results if r.get("status") == "unit_mismatch")
    unknown_count = sum(1 for r in match_results if r.get("status") == "unknown")
    need_check_count = unit_mismatch_count + unknown_count

    # Header (bold supplier and date)
    report = (
        f"\U0001F4E6 *Supplier:* {supplier_str}\n"
        f"\U0001F4C6 *Invoice date:* {date_str}\n"
    )
    report += "────────────────────────────────────────\n"
    # Build table rows
    rows = []
    for idx, r in enumerate(match_results, 1):
        name = escape_md(str(r.get("name", "")), version=2)
        qty = escape_md(str(r.get("qty", "")), version=2)
        unit = escape_md(str(r.get("unit", "")), version=2)
        price = r.get("price")
        status = r.get("status", "unknown")
        if status == "ok":
            status_str = "✅ ok"
        elif status == "unit_mismatch":
            status_str = "⚖️ unit mismatch"
        elif status == "unknown":
            status_str = "❓ not found"
        else:
            status_str = escape_md(str(status), version=2)
        rows.append(_row(idx, name, qty, unit, price, status_str))
    report += build_table(rows) + "\n"
    report += "────────────────────────────────────────\n"
    # Summary (outside code block, no '✅ 0 ok')
    summary = []
    if ok_count > 0:
        summary.append(f"✅ {ok_count} ok")
    if unit_mismatch_count > 0:
        summary.append(f"⚖️ {unit_mismatch_count} unit mismatch")
    if unknown_count > 0:
        summary.append(f"❓ {unknown_count} not found")
    if summary:
        report += "        ".join(summary)
    return report.strip()
