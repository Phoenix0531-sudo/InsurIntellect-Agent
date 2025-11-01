#!/usr/bin/env python3
"""
将分割后的文档块（JSONL）嵌入到 ChromaDB 集合。

输入文件为 JSONL，每行一个对象，至少包含：
- text: 文本内容
- metadata: 元数据字典（可选）
- id: 唯一标识（可选，若缺失则自动生成）
"""

import json
import uuid
from pathlib import Path
from typing import List, Dict
from app.core.app_logging import setup_logging, get_logger

from tqdm import tqdm
from langchain_openai import OpenAIEmbeddings

from app.core.config import settings
from app.core.chromadb_manager import chroma_manager

logger = get_logger(__name__)


def _load_jsonl(file_path: Path) -> List[Dict]:
    """加载 JSONL 文件，跳过损坏行。"""
    items: List[Dict] = []
    with file_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                items.append(obj)
    return items


def embed_chunks_from_file(chunks_file: Path, collection_name: str, batch_size: int = 256) -> None:
    """将 JSONL 文档块嵌入到指定集合。"""
    logger.info("=" * 60)
    logger.info("文档块嵌入到 ChromaDB")
    logger.info("=" * 60)
    logger.info(f"输入文件: {chunks_file}")
    logger.info(f"集合名称: {collection_name}")

    # 初始化嵌入模型（兼容 OpenAI/SiliconFlow 接口）
    embeddings = OpenAIEmbeddings(
        api_key=(settings.OPENAI_API_KEY or settings.SILICONFLOW_API_KEY or ""),
        base_url=(settings.OPENAI_BASE_URL or settings.SILICONFLOW_BASE_URL or ""),
        model=settings.OPENAI_EMBEDDING_MODEL,
        timeout=60,
    )

    # 获取 ChromaDB 集合（单例）
    client = chroma_manager.get_client()
    collection = client.get_collection(collection_name)

    # 加载数据
    items = _load_jsonl(chunks_file)
    total = len(items)
    logger.info(f"待处理文档块: {total}")
    if total == 0:
        logger.warning("⚠️ 未发现有效文档块，结束。")
        return

    processed = 0
    batch_count = 0

    with tqdm(total=total, desc="嵌入进度", unit="条") as pbar:
        for start in range(0, total, batch_size):
            end = min(start + batch_size, total)
            batch = items[start:end]

            texts: List[str] = []
            metadatas: List[Dict] = []
            ids: List[str] = []

            for obj in batch:
                txt = obj.get("text", "")
                meta = obj.get("metadata", {})
                _id = obj.get("id") or str(uuid.uuid4())
                texts.append(txt)
                metadatas.append(meta if isinstance(meta, dict) else {})
                ids.append(str(_id))

            # 计算嵌入
            try:
                vectors = embeddings.embed_documents(texts)
            except Exception as e:
                logger.error(f"❌ 批次嵌入失败: {e}")
                raise

            # 写入集合
            try:
                collection.add(
                    ids=ids,
                    embeddings=vectors,
                    metadatas=metadatas,
                    documents=texts,
                )
            except Exception as e:
                logger.error(f"❌ 批次写入失败: {e}")
                raise

            processed += len(batch)
            batch_count += 1
            pbar.update(len(batch))

    logger.info("\n结果")
    logger.info("-" * 60)
    logger.info(f"✅ 完成！共处理 {processed} 个文档块，分 {batch_count} 个批次写入")
    logger.info(f"📦 持久化目录: {settings.CHROMA_PERSIST_DIRECTORY}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="将分割文档块嵌入到向量数据库")
    parser.add_argument("chunks_file", type=str, help="JSONL 文档块文件路径")
    parser.add_argument("collection_name", type=str, help="ChromaDB 集合名称")
    parser.add_argument("--batch_size", type=int, default=256, help="批量大小")
    args = parser.parse_args()

    setup_logging(level="INFO")
    embed_chunks_from_file(Path(args.chunks_file), args.collection_name, batch_size=args.batch_size)
