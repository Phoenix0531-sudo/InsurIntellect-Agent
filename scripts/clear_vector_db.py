#!/usr/bin/env python3
"""一键清空 Chroma 向量库（持久化目录 + 集合）

用法：
    python scripts/clear_vector_db.py

效果：
    - 删除持久化目录 settings.CHROMA_PERSIST_DIRECTORY
    - 重置并重新创建集合 "insurance_documents"

注意：此操作不可逆，会清除所有已写入的向量数据。
"""

import shutil
from pathlib import Path

from app.core.config import settings
from app.core.chromadb_manager import chroma_manager
from app.core.logging import get_logger

logger = get_logger(__name__)


def main():
    persist_dir = Path(settings.CHROMA_PERSIST_DIRECTORY)
    collection_name = "insurance_documents"

    logger.info(f"准备清空向量库：{persist_dir}（集合：{collection_name}）")

    # 关闭可能存在的客户端引用（本进程）
    try:
        chroma_manager.close()
    except Exception as e:
        logger.warning(f"关闭Chroma客户端失败（可忽略）：{e}")

    # 删除持久化目录
    if persist_dir.exists():
        try:
            shutil.rmtree(persist_dir)
            logger.info(f"已删除持久化目录：{persist_dir}")
        except Exception as e:
            logger.error(f"删除目录失败：{e}")
            return
    else:
        logger.info("持久化目录不存在，无需删除。")

    # 重置并重新创建集合
    try:
        chroma_manager.reset_collection(collection_name)
        logger.info(f"已重置并重新创建集合：{collection_name}")
    except Exception as e:
        logger.warning(f"重置集合时出现问题：{e}，尝试重新初始化后再重置。")
        try:
            # 重新初始化客户端并再次重置集合
            _ = chroma_manager.get_client()
            chroma_manager.reset_collection(collection_name)
            logger.info(f"已重新初始化并重置集合：{collection_name}")
        except Exception as e2:
            logger.error(f"重置集合失败：{e2}")
            return

    logger.info("向量库清理完成。")


if __name__ == "__main__":
    main()

