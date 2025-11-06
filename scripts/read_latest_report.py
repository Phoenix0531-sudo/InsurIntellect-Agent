import json
from pathlib import Path

def main():
    report_dir = Path("reports")
    files = sorted(report_dir.glob("backfill_report_*.json"))
    if not files:
        print("no_report_found")
        return
    latest = files[-1]
    with latest.open("r", encoding="utf-8") as f:
        data = json.load(f)
    print("latest_report:", latest.name)
    print("scanned:", data.get("total_scanned"))
    print("updated:", data.get("total_updated"))
    print("failed:", data.get("total_failed"))
    print("field_update_counts:", data.get("field_update_counts"))
    print("field_presence_counts:", data.get("field_presence_counts"))
    print("complete_4_required_docs:", data.get("complete_4_required_docs"))

if __name__ == "__main__":
    main()

