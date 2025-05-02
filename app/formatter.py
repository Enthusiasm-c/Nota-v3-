from typing import List, Dict

def build_report(parsed_data, match_results: list) -> str:
    # Support both dict and ParsedData object
    supplier = getattr(parsed_data, "supplier", None)
    if supplier is None and isinstance(parsed_data, dict):
        supplier = parsed_data.get("supplier", "?")
    date = getattr(parsed_data, "date", None)
    if date is None and isinstance(parsed_data, dict):
        date = parsed_data.get("date", "?")
    ok_count = sum(1 for r in match_results if r["status"] == "ok")
    need_check_count = sum(1 for r in match_results if r["status"] != "ok")
    total = len(match_results)
    report = f"\U0001F4E6  {supplier} • {date}\n"
    report += "────────────────────────\n"
    report += f"✅ {ok_count} ok\n"
    report += f"⚠️  {need_check_count} need check\n"
    report += f"…\n\n"
    return report
