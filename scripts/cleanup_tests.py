#!/usr/bin/env python3
"""
测试文件自动清理脚本
用于定期清理临时和过期的测试文件
"""

import os
import time
from pathlib import Path
from datetime import datetime
from app.core.app_logging import setup_logging, get_logger

logger = get_logger(__name__)


class TestFileCleanup:
    def __init__(self, root_dir: str = "."):
        self.root_dir = Path(root_dir)
        self.temp_patterns = [
            "temp_test_*.py",
            "debug_*.py",
            "test_*_debug.py",
            "test_*_temp.py",
            "*_test_temp.py",
        ]

        # 核心测试文件，永远不删除
        self.protected_files = {
            "tools/__init__.py",
            "tools/check_db.py",
            "tools/test_api.py",
            "tools/test_rag_workflow.py",
            "tools/test_web_interface.py",
        }

    def is_protected_file(self, file_path: Path) -> bool:
        """检查文件是否为受保护的核心测试文件"""
        try:
            relative_path = str(file_path.relative_to(self.root_dir))
        except ValueError:
            relative_path = str(file_path)
        return relative_path in self.protected_files

    def find_temp_files(self) -> list[Path]:
        """查找所有临时测试文件"""
        temp_files: list[Path] = []
        for pattern in self.temp_patterns:
            for file_path in self.root_dir.rglob(pattern):
                if file_path.is_file() and not self.is_protected_file(file_path):
                    temp_files.append(file_path)
        return temp_files

    def find_old_files(self, days: int = 7) -> list[Path]:
        """查找超过指定天数的测试文件"""
        old_files: list[Path] = []
        cutoff_time = time.time() - days * 24 * 3600

        # 查找所有 test_*.py 文件（递归）
        for file_path in self.root_dir.rglob("test_*.py"):
            if (
                file_path.is_file()
                and not self.is_protected_file(file_path)
                and file_path.stat().st_ctime < cutoff_time
            ):
                old_files.append(file_path)
        return old_files

    def cleanup_files(self, files: list[Path], dry_run: bool = True) -> None:
        """清理文件列表"""
        if not files:
            logger.info("没有找到需要清理的文件")
            return

        logger.info(f"{'[DRY RUN] ' if dry_run else ''}找到 {len(files)} 个文件需要清理")

        for file_path in files:
            file_age = datetime.fromtimestamp(file_path.stat().st_ctime)
            logger.info(f"  - {file_path} (创建于 {file_age.strftime('%Y-%m-%d %H:%M:%S')})")

            if not dry_run:
                try:
                    file_path.unlink()
                    logger.info("    ✅ 已删除")
                except Exception as e:
                    logger.error(f"    ❌ 删除失败: {e}")

    def generate_report(self) -> str:
        """生成清理报告"""
        temp_files = self.find_temp_files()
        old_files = self.find_old_files()
        all_test_files = list(self.root_dir.rglob("test_*.py"))

        report = f"""
# 测试文件清理报告
生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 文件统计
- 总测试文件数: {len(all_test_files)}
- 受保护文件数: {len(self.protected_files)}
- 临时文件数: {len(temp_files)}
- 过期文件数: {len(old_files)}

## 临时文件列表
"""

        if temp_files:
            for file_path in temp_files:
                file_age = datetime.fromtimestamp(file_path.stat().st_ctime)
                report += f"- {file_path} (创建于 {file_age.strftime('%Y-%m-%d')})\n"
        else:
            report += "- 无临时文件\n"

        report += "\n## 过期文件列表\n"

        if old_files:
            for file_path in old_files:
                file_age = datetime.fromtimestamp(file_path.stat().st_ctime)
                report += f"- {file_path} (创建于 {file_age.strftime('%Y-%m-%d')})\n"
        else:
            report += "- 无过期文件\n"

        return report

    def run_cleanup(self, dry_run: bool = True, max_age_days: int = 7) -> None:
        """执行完整的清理流程"""
        logger.info("=" * 50)
        logger.info("测试文件清理工具")
        logger.info("=" * 50)

        # 查找需要清理的文件
        temp_files = self.find_temp_files()
        old_files = self.find_old_files(max_age_days)

        # 合并去重
        all_cleanup_files = list(set(temp_files + old_files))

        if not all_cleanup_files:
            logger.info("✅ 没有找到需要清理的文件")
            return

        # 执行清理
        self.cleanup_files(all_cleanup_files, dry_run)

        if dry_run:
            logger.info("\n💡 这是预览模式，未执行删除")
            logger.info("   要执行实际清理，请使用: python scripts/cleanup_tests.py --execute")
        else:
            logger.info(f"\n✅ 清理完成，共处理 {len(all_cleanup_files)} 个文件")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="测试文件自动清理工具")
    parser.add_argument("--execute", action="store_true", help="执行实际清理（默认预览模式）")
    parser.add_argument("--days", type=int, default=7, help="清理超过指定天数的文件（默认7天）")
    parser.add_argument("--report", action="store_true", help="生成清理报告")

    args = parser.parse_args()

    # 切换到项目根目录
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    os.chdir(project_root)

    cleanup = TestFileCleanup()

    if args.report:
        report = cleanup.generate_report()
        logger.info(report)

        # 保存报告到文件
        report_file = project_root / "test_cleanup_report.md"
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report)
        logger.info(f"\n📄 报告已保存到: {report_file}")
    else:
        cleanup.run_cleanup(dry_run=not args.execute, max_age_days=args.days)


if __name__ == "__main__":
    # 修正日志初始化参数名以兼容 app.core.app_logging.setup_logging
    setup_logging(log_level="INFO")
    main()
