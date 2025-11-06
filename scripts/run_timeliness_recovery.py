import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    from app.core.app_logging import setup_logging
except Exception:
    setup_logging = None


def find_latest_diagnose_report(reports_dir: Path) -> Path | None:
    candidates = sorted(reports_dir.glob("diagnose_timeliness_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def load_groups(report_path: Path) -> list[dict]:
    with report_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    groups = data.get("analyzed_groups") or []
    if not isinstance(groups, list):
        return []
    return groups


def build_targets(groups: list[dict]):
    label_no_date: list[dict] = []
    no_signal: list[dict] = []
    maybe_ocr: list[dict] = []
    for g in groups:
        issue = str(g.get("issue") or "").strip()
        if issue == "标签出现但未匹配到日期":
            label_no_date.append(g)
        elif issue.startswith("文本未出现时效性线索"):
            no_signal.append(g)
        # 启发式：文本极稀疏且未命中日期，可能需要 OCR 重摄取
        try:
            avg_len = float(g.get("avg_text_len") or 0.0)
            has_any_date = bool(g.get("has_any_date"))
            ocr_ratio = float(g.get("ocr_ratio") or 0.0)
            if (avg_len < 120) and (not has_any_date) and (ocr_ratio == 0.0):
                maybe_ocr.append(g)
        except Exception:
            pass
    # 去重（按 file_path 优先，其次 source_file）
    def uniq(items: list[dict]) -> list[dict]:
        seen: set[str] = set()
        out: list[dict] = []
        for it in items:
            fp = str(it.get("file_path") or "").strip()
            sf = str(it.get("source_file") or "").strip()
            key = fp or ("name:" + sf) if sf else json.dumps(it, ensure_ascii=False)
            if key not in seen:
                seen.add(key)
                out.append(it)
        return out
    return uniq(label_no_date), uniq(no_signal), uniq(maybe_ocr)


def run_cmd(cmd: list[str], dry_run: bool, cwd: Path) -> int:
    print("$", " ".join(cmd))
    if dry_run:
        return 0
    proc = subprocess.run(cmd, cwd=str(cwd))
    return proc.returncode


def main():
    parser = argparse.ArgumentParser(description="Run incremental timeliness backfill based on latest diagnose report")
    parser.add_argument("--reports-dir", default="reports", help="Reports directory")
    parser.add_argument("--neighbor-window-label", type=int, default=700, help="Neighbor window for label-no-date files")
    parser.add_argument("--max-content-chars-label", type=int, default=12000, help="Max content chars for label-no-date files")
    parser.add_argument("--neighbor-window-nosignal", type=int, default=600, help="Neighbor window for no-signal files")
    parser.add_argument("--max-content-chars-nosignal", type=int, default=15000, help="Max content chars for no-signal files")
    parser.add_argument("--enable-ocr-reingest", action="store_true", help="Enable OCR reingest for suspected sparse-text files")
    parser.add_argument("--keep-latest-count", type=int, default=3, help="Keep N latest reports per type during cleanup")
    parser.add_argument("--dry-run", action="store_true", help="Print commands only")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    cwd = Path.cwd()
    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    log_file = reports_dir / f"run_timeliness_recovery_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    if setup_logging:
        try:
            setup_logging(log_level=args.log_level, log_file=str(log_file))
        except TypeError:
            # 兼容旧签名
            setup_logging(args.log_level, str(log_file))

    latest = find_latest_diagnose_report(reports_dir)
    if not latest:
        print("未找到诊断报告 diagnose_timeliness_*.json，请先运行 scripts/diagnose_timeliness.py")
        sys.exit(1)
    print(f"使用诊断报告: {latest}")

    groups = load_groups(latest)
    label_no_date, no_signal, maybe_ocr = build_targets(groups)
    print(f"标签命中未匹配日期: {len(label_no_date)} 条；文本无线索: {len(no_signal)} 条；疑似需要 OCR: {len(maybe_ocr)} 条")

    # 第1步：针对“标签命中但未匹配到日期”增量回填
    for g in label_no_date:
        fp = str(g.get("file_path") or "").strip()
        sf = str(g.get("source_file") or "").strip()
        # 尝试 file_path 和 source_file 两种过滤，兼容路径分隔差异
        for where in ([{"file_path": fp}] if fp else []) + ([{"source_file": sf}] if sf else []):
            where_json = json.dumps(where, ensure_ascii=False)
            cmd = [
                sys.executable,
                "scripts/backfill_metadata.py",
                "--where-json", where_json,
                "--neighbor-window", str(args.neighbor_window_label),
                "--max-content-chars", str(args.max_content_chars_label),
                "--report-dir", str(reports_dir),
            ]
            rc = run_cmd(cmd, args.dry_run, cwd)
            if rc != 0:
                print(f"回填失败（label_no_date）：{where}")

    # 第2步：针对“文本无线索”提升内容长度与窗口
    for g in no_signal:
        fp = str(g.get("file_path") or "").strip()
        sf = str(g.get("source_file") or "").strip()
        for where in ([{"file_path": fp}] if fp else []) + ([{"source_file": sf}] if sf else []):
            where_json = json.dumps(where, ensure_ascii=False)
            cmd = [
                sys.executable,
                "scripts/backfill_metadata.py",
                "--where-json", where_json,
                "--neighbor-window", str(args.neighbor_window_nosignal),
                "--max-content-chars", str(args.max_content_chars_nosignal),
                "--report-dir", str(reports_dir),
            ]
            rc = run_cmd(cmd, args.dry_run, cwd)
            if rc != 0:
                print(f"回填失败（no_signal）：{where}")

    # 第3步（可选）：OCR 重摄取
    if args.enable_ocr_reingest and maybe_ocr:
        for g in maybe_ocr:
            fp = str(g.get("file_path") or "").strip()
            sf = str(g.get("source_file") or "").strip()
            where = {"file_path": fp} if fp else ({"source_file": sf} if sf else None)
            if not where:
                continue
            where_json = json.dumps(where, ensure_ascii=False)
            cmd = [
                sys.executable,
                "ingest.py",
                "--reingest",
                "--where-json", where_json,
                "--report-dir", str(reports_dir),
            ]
            rc = run_cmd(cmd, args.dry_run, cwd)
            if rc != 0:
                print(f"OCR 重摄取失败：{fp or sf}")

    # 第4步：报告清理，仅保留最新 N 份
    def cleanup_pattern(pattern: str, keep: int):
        files = sorted(reports_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        to_delete = files[keep:]
        for p in to_delete:
            print(f"删除旧报告: {p}")
            if not args.dry_run:
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass

    k = max(args.keep_latest_count, 1)
    # 成对清理：json/md 与 html
    cleanup_pattern("diagnose_timeliness_*.json", k)
    cleanup_pattern("diagnose_timeliness_*.md", k)
    cleanup_pattern("backfill_report_*.json", k)
    cleanup_pattern("backfill_report_*.html", k)
    cleanup_pattern("ranking_report_*.json", k)
    cleanup_pattern("ranking_report_*.html", k)

    print("完成 timeliness 恢复流程。")


if __name__ == "__main__":
    main()
