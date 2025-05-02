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
    ok_count = sum(1 for r in match_results if r["status"] == "ok")
    need_check_count = sum(1 for r in match_results if r["status"] != "ok")
    report = f"{supplier_str} • {date_str}\n"
    report += "────────────────────────────────\n"
    # Table header (monospace)
    report += "```\n"
    report += f"#{'NAME'.ljust(20)} {'QTY'.ljust(5)} {'UNIT'.ljust(6)} {'PRICE'.ljust(8)}  STATUS\n"
    # Table rows
    for idx, r in enumerate(match_results):
        name = str(r.get("name", "")).ljust(20)
        qty = str(r.get("qty", "")).ljust(5)
        unit = str(r.get("unit", "")).ljust(6)
        price = str(r.get("price", "—")).ljust(8)
        status = r.get("status", "unknown")
        if status == "ok":
            status_str = "✅ ok"
        elif status == "unit_mismatch":
            status_str = "⚖️ unit mismatch"
        elif status == "unknown":
            status_str = "❓ not found"
        else:
            status_str = status
        report += f"{idx+1} {name} {qty} {unit} {price}  {status_str}\n"
    report += "```\n"
    # Summary
    if ok_count > 0:
        report += f"✅ {ok_count} ok\n"
    report += f"⚠️  {need_check_count} need check\n"
    return report
