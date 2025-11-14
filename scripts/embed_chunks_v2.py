#!/usr/bin/env python3
"""
使用付费嵌入模型为原始数据重新生成向量并写入 ChromaDB，支持：
 - 分批次提交（默认每批 1000 条）
 - 写入进度监控与断点续传（checkpoint）
 - 失败条目记录与重试机制
 - 保留原始数据与向量ID映射（输出 JSONL）

输入格式（JSONL）：每行一个对象，至少包含：
  {
    "id": "chunk_001",           # 原始ID（建议唯一），将作为向量ID
    "text": "段落内容...",         # 文本内容
    "metadata": { ... }           # 可选元数据
  }

示例调用：
  python scripts/embed_chunks_v2.py \
    --input data/chunks.jsonl \
    --persist_dir data/chroma/new_space \
    --collection clauses_v2 \
    --embedding_model BAAI/bge-m3 \
    --batch_size 1000 \
    --checkpoint .chk/emb_v2.json \
    --mapping_out logs/mapping_v2.jsonl \
    --reset_collection
"""

import os
import json
import time
import argparse
from typing import List, Dict, Any

import chromadb
from chromadb.utils import embedding_functions


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                items.append(obj)
            except Exception:
                # 跳过损坏行，但在后续失败记录
                pass
    return items


def save_checkpoint(path: str, data: Dict[str, Any]):
    if not path:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_checkpoint(path: str) -> Dict[str, Any]:
    if not path or not os.path.exists(path):
        return {"processed_ids": [], "failed_ids": [], "last_index": 0}
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return {"processed_ids": [], "failed_ids": [], "last_index": 0}


def append_mapping(path: str, mapping: Dict[str, Any]):
    if not path:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(mapping, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser(description="批量嵌入并写入 ChromaDB")
    parser.add_argument("--input", required=True, help="JSONL 原始数据文件")
    parser.add_argument("--persist_dir", required=True, help="ChromaDB 持久化目录（新空间）")
    parser.add_argument("--collection", required=True, help="集合名称")
    parser.add_argument("--embedding_model", default="BAAI/bge-m3", help="嵌入模型（支持 SiliconFlow/OpenAI 兼容接口）")
    parser.add_argument("--batch_size", type=int, default=1000, help="每批次写入数")
    parser.add_argument("--checkpoint", default="", help="断点续传 checkpoint 文件路径")
    parser.add_argument("--mapping_out", default="", help="原始ID与向量ID映射输出 JSONL 路径")
    parser.add_argument("--reset_collection", action="store_true", help="若集合存在则重置")
    parser.add_argument("--retry_failures", action="store_true", help="读取 checkpoint 并重试失败条目")
    args = parser.parse_args()

    # 环境变量：兼容 OPENAI/SiliconFlow
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("SILICONFLOW_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("SILICONFLOW_BASE_URL")
    if not api_key:
        raise RuntimeError("未检测到 OPENAI_API_KEY 或 SILICONFLOW_API_KEY")

    # 加载数据与 checkpoint
    items = load_jsonl(args.input)
    checkpoint = load_checkpoint(args.checkpoint)
    processed_ids = set(checkpoint.get("processed_ids", []))
    failed_ids = set(checkpoint.get("failed_ids", []))

    # 初始化 Chroma 客户端与集合
    os.makedirs(args.persist_dir, exist_ok=True)
    client = chromadb.PersistentClient(path=args.persist_dir)

    ef = embedding_functions.OpenAIEmbeddingFunction(
        api_key=api_key,
        api_base=base_url,
        model_name=args.embedding_model,
    )

    if args.reset_collection:
        try:
            client.delete_collection(args.collection)
        except Exception:
            pass

    try:
        collection = client.get_collection(name=args.collection)
    except Exception:
        collection = client.create_collection(name=args.collection, metadata={"embedding_model": args.embedding_model}, embedding_function=ef)
    else:
        # 确保集合配置了嵌入函数
        collection = client.get_collection(name=args.collection, embedding_function=ef)

    # 记录损坏行的失败
    valid_items = []
    corrupt_count = 0
    for obj in items:
        if not isinstance(obj, dict):
            corrupt_count += 1
            continue
        oid = obj.get("id") or obj.get("chunk_id")
        text = obj.get("text") or obj.get("content")
        if not oid or not text:
            corrupt_count += 1
            continue
        valid_items.append({"id": str(oid), "text": str(text), "metadata": obj.get("metadata", {})})

    total = len(valid_items)
    print(f"加载有效条目: {total}, 损坏/缺失: {corrupt_count}")

    # 若仅重试失败
    if args.retry_failures and failed_ids:
        valid_items = [it for it in valid_items if it["id"] in failed_ids]
        total = len(valid_items)
        print(f"仅重试失败条目，总数: {total}")

    # 批量写入
    batch_size = max(1, int(args.batch_size))
    start = time.perf_counter()
    written = 0
    new_failed = []

    for i in range(0, total, batch_size):
        batch = valid_items[i:i + batch_size]
        ids = [b["id"] for b in batch if b["id"] not in processed_ids]
        docs = [b["text"] for b in batch if b["id"] not in processed_ids]
        metas = [b.get("metadata", {}) for b in batch if b["id"] not in processed_ids]

        if not ids:
            continue

        try:
            collection.add(ids=ids, documents=docs, metadatas=metas)
        except Exception as e:
            print(f"[批次失败] i={i} size={len(ids)} err={e}")
            new_failed.extend(ids)
            # 写入 checkpoint
            checkpoint["failed_ids"] = list(set(checkpoint.get("failed_ids", []) + new_failed))
            save_checkpoint(args.checkpoint, checkpoint)
            continue

        # 成功写入：更新映射与进度
        for oid in ids:
            append_mapping(args.mapping_out, {"original_id": oid, "vector_id": oid})
            processed_ids.add(oid)
        written += len(ids)
        checkpoint["processed_ids"] = list(processed_ids)
        checkpoint["last_index"] = i + len(batch)
        save_checkpoint(args.checkpoint, checkpoint)

        elapsed = time.perf_counter() - start
        qps = written / elapsed if elapsed > 0 else 0
        print(f"progress: {written}/{total} ({written/total*100:.2f}%), qps={qps:.2f}")

    # 完成统计
    elapsed = time.perf_counter() - start
    print("=== 写入完成 ===")
    print(f"成功: {written}, 失败: {len(new_failed)}, 总耗时: {elapsed:.2f}s, 吞吐: {written/elapsed if elapsed>0 else 0:.2f} doc/s")
    if new_failed:
        print(f"失败ID样例: {new_failed[:10]}")


if __name__ == "__main__":
    main()

