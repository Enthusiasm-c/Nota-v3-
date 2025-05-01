from typing import List, Dict

def build_report(parsed_data: dict, match_results: List[Dict]) -> str:
    supplier = parsed_data.get("supplier", "?")
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
