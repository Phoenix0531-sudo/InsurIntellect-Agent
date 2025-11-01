#!/usr/bin/env python3
"""
强制重置 ChromaDB - 完全删除数据目录
"""

import shutil
from pathlib import Path
from app.core.config import settings
from app.core.app_logging import setup_logging, get_logger

logger = get_logger(__name__)


def force_reset_chromadb() -> bool:
    """强制重置 ChromaDB，删除整个数据目录并重新创建空目录。"""
    logger.info("=" * 60)
    logger.info("ChromaDB 强制重置")
    logger.info("=" * 60)

    chroma_dir = Path(settings.CHROMA_PERSIST_DIRECTORY)
    logger.info(f"🔄 强制删除 ChromaDB 数据目录: {chroma_dir}")

    if chroma_dir.exists():
        try:
            shutil.rmtree(chroma_dir)
            logger.info(f"✅ 成功删除目录: {chroma_dir}")
        except Exception as e:
            logger.error(f"❌ 删除目录失败: {e}")
            return False
    else:
        logger.info(f"ℹ️  目录不存在: {chroma_dir}")

    # 重新创建空目录
    try:
        chroma_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"✅ 重新创建空目录: {chroma_dir}")
    except Exception as e:
        logger.error(f"❌ 创建目录失败: {e}")
        return False

    logger.info("\n重置结果")
    logger.info("=" * 60)
    logger.info("✅ ChromaDB 强制重置成功")
    logger.info("\n📋 下一步")
    logger.info("   1. 运行嵌入脚本重新构建向量数据")
    logger.info("   2. 使用: python scripts/embed_chunks.py <chunks_file> <collection_name>")

    return True


if __name__ == "__main__":
    setup_logging(level="INFO")
    force_reset_chromadb()
