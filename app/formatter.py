def build_report(parsed_data, match_results: list) -> str:
    # Support both dict and ParsedData object
    supplier = getattr(parsed_data, "supplier", None)
    if supplier is None and isinstance(parsed_data, dict):
        supplier = parsed_data.get("supplier", None)
    date = getattr(parsed_data, "date", None)
    if date is None and isinstance(parsed_data, dict):
        date = parsed_data.get("date", None)
    supplier_str = "Unknown supplier" if not supplier else str(supplier)
    date_str = "—" if not date else str(date)
    ok_count = sum(1 for r in match_results if r.get("status") == "ok")
    need_check_count = sum(1 for r in match_results if r.get("status") != "ok")

    # Header (bold supplier and date)
    report = (
        f"\U0001F4E6 *Supplier:* {supplier_str}\n"
        f"\U0001F4C6 *Invoice date:* {date_str}\n"
    )
    # Single divider
    report += "────────────────────────────────────────\n"
    # Table in code block, fixed width
    report += "`\n"
    report += "`#  NAME                     QTY  UNIT  PRICE      STATUS`\n"
    for idx, r in enumerate(match_results, 1):
        name = str(r.get("name", ""))
        if len(name) > 22:
            name = name[:22] + "…"
        name = name.ljust(24)
        qty = str(r.get("qty", "")).rjust(5)
        unit = str(r.get("unit", "")).ljust(6)
        price = r.get("price")
        price_str = f"{price:,}" if price not in (None, "", "-") else "—"
        price_str = price_str.rjust(8)
        status = r.get("status", "unknown")
        if status == "ok":
            status_str = "✅ ok"
        elif status == "unit_mismatch":
            status_str = "⚖️ unit mismatch"
        elif status == "unknown":
            status_str = "❓ not found"
        else:
            status_str = str(status)
        report += f"`{idx:<3} {name}{qty} {unit}{price_str}  {status_str}`\n"
    report += "`\n"
    report += "────────────────────────────────────────\n"
    # Summary (outside code block, no '✅ 0 ok')
    summary = []
    if ok_count > 0:
        summary.append(f"✅ {ok_count} ok")
    if need_check_count > 0:
        summary.append(f"⚠️ {need_check_count} need check")
    if summary:
        report += "        ".join(summary)
    return report.strip()
