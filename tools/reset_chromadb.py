#!/usr/bin/env python3
"""
重置 ChromaDB 集合
"""

import sys
import os
from app.core.app_logging import setup_logging, get_logger

# 添加项目路径，确保可以导入 app 包
sys.path.insert(0, os.path.abspath('.'))

# 模块级 logger
logger = get_logger(__name__)


def reset_chromadb() -> bool:
    """重置 ChromaDB 集合，删除并验证删除成功"""

    logger.info("🔄 重置 ChromaDB 集合...")

    try:
        from app.core.chromadb_manager import chroma_manager

        # 获取 ChromaDB 客户端
        client = chroma_manager.get_client()

        # 检查集合是否存在
        try:
            collection = client.get_collection("insurance_documents")
            logger.info(f"✅ 已找到现有集合: {collection.name}")
            logger.info(f"   向量数量: {collection.count()}")

            # 删除集合
            client.delete_collection("insurance_documents")
            logger.info("✅ 成功删除现有集合")

        except Exception as e:
            logger.info(f"ℹ️ 集合不存在或已删除: {e}")

        # 验证集合已删除
        try:
            client.get_collection("insurance_documents")
            logger.warning("⚠️ 集合仍然存在")
            return False
        except Exception:
            logger.info("✅ 确认集合已删除")
            return True

    except Exception as e:
        logger.exception(f"❌ 重置失败: {e}")
        return False


def main():
    """主函数"""

    setup_logging(level="INFO")
    logger.info("=" * 60)
    logger.info("ChromaDB 集合重置")
    logger.info("=" * 60)

    success = reset_chromadb()

    logger.info("\n" + "=" * 60)
    logger.info("重置结果")
    logger.info("=" * 60)

    if success:
        logger.info("✅ ChromaDB 集合重置成功")
        logger.info("\n📋 下一步")
        logger.info("   1. 运行嵌入脚本重新构建向量数据")
        logger.info("   2. 使用 python scripts/embed_chunks.py")
    else:
        logger.error("❌ ChromaDB 集合重置失败")


if __name__ == "__main__":
    main()
