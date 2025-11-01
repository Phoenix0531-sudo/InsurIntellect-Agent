#!/usr/bin/env python3
"""检查 ChromaDB 数据库状态"""

import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings
from app.core.chromadb_manager import chroma_manager
from app.core.app_logging import setup_logging, get_logger


def main():
    logger = setup_logging()
    logger.info(f"ChromaDB 持久化目录: {settings.CHROMA_PERSIST_DIRECTORY}")

    # 检查目录是否存在
    persist_dir = Path(settings.CHROMA_PERSIST_DIRECTORY)
    logger.info(f"目录是否存在: {persist_dir.exists()}")

    if persist_dir.exists():
        files = list(persist_dir.glob("*"))
        logger.info(f"目录中的文件数量: {len(files)}")
        for file in files[:10]:  # 只显示前 10 个文件
            logger.info(f"  - {file.name}")

    try:
        # 获取集合
        collection = chroma_manager.get_collection("insurance_documents")
        count = collection.count()
        logger.info(f"集合中的文档数量: {count}")

        if count > 0:
            # 获取前几个文档
            result = collection.get(limit=3, include=["documents", "metadatas"])
            logger.info("示例文档:")
            for i, (doc, meta) in enumerate(zip(result.get("documents", []), result.get("metadatas", []))):
                logger.info(f"  文档 {i+1}: {doc[:100]}...")
                logger.info(f"  元数据: {meta}")

    except Exception as e:
        logger.error(f"获取集合信息时出错: {e}")


if __name__ == "__main__":
    main()
