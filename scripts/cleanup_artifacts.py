#!/usr/bin/env python3
"""
通用制品清理脚本：清理旧报告与日志

功能：
- 清理 reports/ 目录下超过阈值天数的 backfill 与 ranking 报告（.json/.html）
- 清理 logs/ 目录下超过阈值天数的日志文件
- 预览与执行模式可选

用法：
python scripts/cleanup_artifacts.py --days 14            # 预览清理超过14天的制品
python scripts/cleanup_artifacts.py --days 30 --execute  # 实际清理超过30天的制品
python scripts/cleanup_artifacts.py --report             # 只生成清理报告
"""

import os
import time
from pathlib import Path
from datetime import datetime

from app.core.app_logging import setup_logging, get_logger

logger = get_logger(__name__)


class ArtifactCleanup:
    def __init__(self, project_root: str = "."):
        self.root = Path(project_root)
        self.report_dir = self.root / "reports"
        self.logs_dir = self.root / "logs"

        # 需要清理的文件模式
        self.report_patterns = [
            "backfill_report_*.json",
            "backfill_report_*.html",
            "ranking_report_*.json",
            "ranking_report_*.html",
        ]
        self.log_patterns = ["*.log"]

    def _find_files(self, base: Path, patterns: list[str], cutoff: float) -> list[Path]:
        results: list[Path] = []
        for pat in patterns:
            for fp in base.rglob(pat):
                try:
                    if fp.is_file() and fp.stat().st_ctime < cutoff:
                        results.append(fp)
                except Exception:
                    continue
        return results

    def collect(self, days: int) -> dict[str, list[Path]]:
        cutoff = time.time() - days * 24 * 3600
        to_delete_reports = self._find_files(self.report_dir, self.report_patterns, cutoff) if self.report_dir.exists() else []
        to_delete_logs = self._find_files(self.logs_dir, self.log_patterns, cutoff) if self.logs_dir.exists() else []
        return {"reports": to_delete_reports, "logs": to_delete_logs}

    def cleanup(self, files: list[Path], dry_run: bool = True) -> None:
        if not files:
            return
        for fp in files:
            age = datetime.fromtimestamp(fp.stat().st_ctime).strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"  - {fp} (创建于 {age})")
            if not dry_run:
                try:
                    fp.unlink()
                    logger.info("    ✅ 已删除")
                except Exception as e:
                    logger.warning(f"    ❌ 删除失败: {e}")

    def generate_report(self, days: int) -> str:
        collected = self.collect(days)
        total_reports = len(collected["reports"])
        total_logs = len(collected["logs"])
        report = [
            f"# 制品清理报告",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"阈值: {days} 天",
            "",
            f"- 待清理报告文件: {total_reports}",
            f"- 待清理日志文件: {total_logs}",
            "",
            "## 报告文件列表",
        ]
        if total_reports:
            for fp in collected["reports"]:
                report.append(f"- {fp}")
        else:
            report.append("- 无")
        report += ["", "## 日志文件列表"]
        if total_logs:
            for fp in collected["logs"]:
                report.append(f"- {fp}")
        else:
            report.append("- 无")
        return "\n".join(report)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="制品清理脚本：清理旧报告与日志")
    parser.add_argument("--days", type=int, default=14, help="清理超过指定天数的文件（默认14天）")
    parser.add_argument("--execute", action="store_true", help="执行实际清理（默认预览模式）")
    parser.add_argument("--report", action="store_true", help="仅生成清理报告")
    args = parser.parse_args()

    # 切换到项目根目录
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    os.chdir(project_root)

    setup_logging(level="INFO")

    cleaner = ArtifactCleanup(project_root=str(project_root))

    if args.report:
        rpt = cleaner.generate_report(days=args.days)
        logger.info("\n" + rpt)
        out = project_root / "artifact_cleanup_report.md"
        with open(out, "w", encoding="utf-8") as f:
            f.write(rpt)
        logger.info(f"📄 报告已保存: {out}")
        return

    collected = cleaner.collect(days=args.days)
    logger.info("准备清理以下文件：")
    logger.info(f"- 报告文件: {len(collected['reports'])}")
    logger.info(f"- 日志文件: {len(collected['logs'])}")

    # 预览/执行
    dry_run = not args.execute
    cleaner.cleanup(collected["reports"], dry_run=dry_run)
    cleaner.cleanup(collected["logs"], dry_run=dry_run)

    if dry_run:
        logger.info("\n💡 当前为预览模式，未执行删除。使用 --execute 开启实际清理。")
    else:
        logger.info("\n✅ 清理完成。")


if __name__ == "__main__":
    main()

