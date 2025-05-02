
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
    report = f"\U0001F4E6  {supplier_str} • {date_str}\n"
    report += "────────────────────────────────\n"
    if ok_count > 0:
        report += f"✅ {ok_count} ok\n"
    report += f"⚠️  {need_check_count} need check\n\n"
    # List every position with its status
    for idx, r in enumerate(match_results):
        name = r.get("name", "?")
        status = r.get("status", "unknown")
        if status == "ok":
            status_str = "✅ ok"
        elif status == "unit_mismatch":
            status_str = "❗ unit mismatch"
        else:
            status_str = "⚠️ unknown"
        report += f"{idx+1}. {name} — {status_str}\n"
    return report
