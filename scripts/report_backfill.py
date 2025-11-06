import os
import json
import glob
import datetime


def summarize_backfill_reports(base_dir: str = "reports/backfill") -> dict:
    latest_file = None
    latest_mtime = 0.0
    if os.path.isdir(base_dir):
        for p in glob.glob(os.path.join(base_dir, "*.json")):
            try:
                m = os.path.getmtime(p)
                if m > latest_mtime:
                    latest_mtime = m
                    latest_file = p
            except Exception:
                continue
    result: dict = {
        "has_report_dir": os.path.isdir(base_dir),
        "latest_report_file": latest_file,
        "latest_report_mtime": datetime.datetime.fromtimestamp(latest_mtime).isoformat() if latest_mtime else None,
    }
    if latest_file:
        try:
            with open(latest_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            result["summary"] = {
                "updated_count": data.get("updated_count") or data.get("updated", 0),
                "failed_count": data.get("failed_count") or data.get("failed", 0),
                "skipped_count": data.get("skipped_count") or data.get("skipped", 0),
                "verify_complete_ratio": (data.get("verify") or {}).get("complete_ratio"),
                "date_source_stats": data.get("date_source_stats") or {},
                "duration_seconds": data.get("duration_seconds"),
            }
        except Exception as e:
            result["error"] = f"read_report_failed: {e}"
    return result


if __name__ == "__main__":
    res = summarize_backfill_reports()
    print(json.dumps(res, ensure_ascii=False))

