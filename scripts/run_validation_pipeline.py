#!/usr/bin/env python3
"""
自动化执行流程：
- 运行一次性元数据补全脚本（backfill_metadata.py）
- 运行排序验证脚本（validate_ranking.py）
- 汇总日志并进行结果通知
"""

import os
import subprocess
import sys
from datetime import datetime

from app.core.app_logging import setup_logging


def run_cmd(cmd: list) -> int:
    return subprocess.call(cmd, shell=False)


def main():
    report_dir = os.environ.get("REPORT_DIR", "reports")
    os.makedirs(report_dir, exist_ok=True)
    logger = setup_logging(log_level=os.environ.get("LOG_LEVEL", "INFO"), log_file=os.path.join(report_dir, "pipeline.log"))

    logger.info("启动自动化验证管线")

    code1 = run_cmd([sys.executable, "scripts/backfill_metadata.py", "--batch-size", "500", "--report-dir", report_dir])
    if code1 != 0:
        logger.error("backfill_metadata 执行失败")

    code2 = run_cmd([sys.executable, "tools/validate_ranking.py", "--cases", "tools/ranking_test_cases.json", "--report-dir", report_dir])
    if code2 != 0:
        logger.error("validate_ranking 执行失败")

    logger.info("自动化管线执行结束")


if __name__ == "__main__":
    main()

