#!/usr/bin/env python3
"""
检查嵌入模型维度与 ChromaDB 集合维度
"""

import sys
import os
from app.core.app_logging import setup_logging, get_logger

# 添加项目路径
sys.path.insert(0, os.path.abspath('.'))

# 模块级 logger（具体配置在 main 中）
logger = get_logger(__name__)


def check_embedding_dimensions() -> int | None:
    """检查嵌入模型维度。返回维度或 None。"""

    logger.info("🔍 检查嵌入模型维度...")
    try:
        from app.core.config import settings
        from langchain_openai import OpenAIEmbeddings

        # 环境变量（用于 SiliconFlow 兼容接口）
        os.environ["OPENAI_API_KEY"] = settings.SILICONFLOW_API_KEY or (settings.OPENAI_API_KEY or "")
        os.environ["OPENAI_BASE_URL"] = settings.OPENAI_BASE_URL or settings.SILICONFLOW_BASE_URL or ""

        embeddings = OpenAIEmbeddings(
            model=settings.OPENAI_EMBEDDING_MODEL,
            api_key=os.environ["OPENAI_API_KEY"],
            base_url=os.environ["OPENAI_BASE_URL"],
        )

        test_text = "这是一个测试文本"
        vector = embeddings.embed_query(test_text)
        logger.info("✅ 嵌入模型工作正常")
        logger.info(f"   模型: {settings.OPENAI_EMBEDDING_MODEL}")
        logger.info(f"   向量维度: {len(vector)}")
        return len(vector)

    except Exception as e:
        logger.exception(f"❌ 嵌入模型测试失败: {e}")
        return None


def check_chromadb_collection() -> int | None:
    """检查 ChromaDB 集合信息并返回样本向量维度。"""

    logger.info("\n🔍 检查 ChromaDB 集合...")
    try:
        from app.core.chromadb_manager import chroma_manager

        client = chroma_manager.get_client()
        collection = client.get_collection("insurance_documents")

        logger.info("✅ ChromaDB 集合信息:")
        logger.info(f"   集合名称: {collection.name}")
        try:
            count = collection.count()
        except Exception:
            count = -1
        logger.info(f"   向量数量: {count}")

        # 尝试获取样本向量维度
        try:
            results = collection.get(limit=1, include=["embeddings"])
            embeddings = results.get("embeddings", [])

            # 兼容 list / numpy 数组等类型的判断
            try:
                import numpy as np  # type: ignore
            except Exception:
                np = None  # noqa: N816

            if isinstance(embeddings, list):
                arr = embeddings
            elif np is not None and hasattr(embeddings, "shape"):
                # 可能是 numpy 数组
                arr = embeddings.tolist()
            else:
                # 回退为可迭代转换
                try:
                    arr = list(embeddings) if embeddings is not None else []
                except Exception:
                    arr = []

            if len(arr) > 0:
                sample = arr[0]
                try:
                    dim = len(sample)
                except Exception:
                    # 某些情况下 sample 可能是 numpy 数组或嵌套结构
                    dim = int(getattr(sample, "shape", [0])[0] or 0)
                logger.info(f"   存储的向量维度: {dim}")
                return dim
            else:
                logger.warning("   ⚠️ 集合中没有向量数据")
                return None
        except Exception as e:
            logger.warning(f"   ⚠️ 获取向量数据失败: {e}")
            return None

    except Exception as e:
        logger.exception(f"❌ ChromaDB 检查失败: {e}")
        return None


def main():
    setup_logging(level="INFO")
    logger.info("=" * 60)
    logger.info("嵌入维度诊断")
    logger.info("=" * 60)

    current_dim = check_embedding_dimensions()
    stored_dim = check_chromadb_collection()

    logger.info("\n" + "=" * 60)
    logger.info("诊断结果")
    logger.info("=" * 60)

    if current_dim and stored_dim:
        if current_dim == stored_dim:
            logger.info("✅ 嵌入维度匹配")
        else:
            logger.error("❌ 嵌入维度不匹配！")
            logger.info(f"   当前模型维度: {current_dim}")
            logger.info(f"   存储的维度: {stored_dim}")
            logger.info("\n🔧 解决方案:")
            logger.info("   1. 更换嵌入模型以匹配存储的维度")
            logger.info("   2. 或者重新构建向量数据库")
    else:
        logger.error("❌ 无法完成诊断，请检查上述错误")


if __name__ == "__main__":
    main()
