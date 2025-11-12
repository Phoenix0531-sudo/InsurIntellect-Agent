#!/usr/bin/env python3
"""
检查 ChromaDB 集合的元数据
"""

import sys
import os
from app.core.app_logging import setup_logging, get_logger

# 添加项目路径
sys.path.insert(0, os.path.abspath('.'))

# 初始化模块级 logger（具体配置在 main 中完成）
logger = get_logger(__name__)


def check_chromadb_metadata() -> bool:
    """检查 ChromaDB 集合元数据。"""

    logger.info("🔍 检查 ChromaDB 集合元数据...")

    try:
        from app.core.chromadb_manager import chroma_manager

        # 获取 ChromaDB 客户端
        client = chroma_manager.get_client()

        # 获取集合
        collection = client.get_collection("insurance_documents")

        logger.info("✅ ChromaDB 集合基本信息:")
        logger.info(f"   集合名称: {collection.name}")
        try:
            count = collection.count()
        except Exception:
            count = -1
        logger.info(f"   向量数量: {count}")

        # 获取集合的元数据
        metadata = getattr(collection, "metadata", {})
        logger.info(f"   集合元数据: {metadata}")

        # 尝试获取一些 ID 来检查
        try:
            results = collection.get(limit=5, include=["metadatas", "ids"])
            ids = results.get("ids", []) or []
            logger.info(f"   样本文档 ID: {ids[:5] if ids else '无'}")
            metadatas = results.get("metadatas", [])
            if metadatas:
                logger.info(f"   样本元数据: {metadatas[0] if metadatas else '无'}")
        except Exception as e:
            logger.warning(f"   ⚠️ 获取文档信息失败: {e}")

        return True

    except Exception as e:
        logger.exception(f"❌ ChromaDB 检查失败: {e}")
        return False


def check_embedding_model_info() -> bool:
    """检查当前配置的嵌入模型信息。"""

    logger.info("\n🔍 检查嵌入模型配置...")

    try:
        from app.core.config import settings

        logger.info("✅ 嵌入模型配置:")
        logger.info(f"   OPENAI_EMBEDDING_MODEL: {settings.OPENAI_EMBEDDING_MODEL}")
        logger.info(f"   EMBEDDING_MODEL: {getattr(settings, 'EMBEDDING_MODEL', 'N/A')}")
        logger.info(f"   SILICONFLOW_API_KEY: {'已设置' if settings.SILICONFLOW_API_KEY else '未设置'}")
        logger.info(f"   SILICONFLOW_BASE_URL: {settings.SILICONFLOW_BASE_URL}")

        return True

    except Exception as e:
        logger.error(f"❌ 配置检查失败: {e}")
        return False


def main():
    """主函数。"""

    setup_logging(log_level="INFO")
    logger.info("=" * 60)
    logger.info("ChromaDB 元数据检查")
    logger.info("=" * 60)

    # 检查嵌入模型配置
    check_embedding_model_info()

    # 检查 ChromaDB 元数据
    check_chromadb_metadata()

    logger.info("\n" + "=" * 60)
    logger.info("分析与建议")
    logger.info("=" * 60)

    logger.info("根据之前的错误信息：")
    logger.info("- 嵌入维度不匹配问题")
    logger.info("  当前模型 BAAI/bge-m3 产生 1024 维向量")
    logger.info("  而 ChromaDB 集合可能期望 384 维向量")
    logger.info("- 这说明之前使用的是不同的嵌入模型")

    logger.info("\n🔧 解决方案:")
    logger.info("  1. 选项一：使用 384 维的嵌入模型")
    logger.info("  2. 选项二：重新构建向量数据库（推荐）")
    logger.info("  3. 选项三：删除现有集合并重新嵌入文档")


if __name__ == "__main__":
    main()
