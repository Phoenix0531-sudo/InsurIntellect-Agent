#!/usr/bin/env python3
"""
ChromaDB 检索基准测试：在不同 n_results 与查询集上评估延迟与近似召回。

用法：
  python tools/benchmark_vector_search.py --persist_dir data/chroma/new_space --collection clauses_v2 --queries data/queries.jsonl

queries.jsonl 每行：{"text": "用户问题...", "expected_ids": ["id1", "id2"]}（可选 expected_ids）
输出：各 n_results 下的平均延迟、P95、P99 与估计召回（若提供 expected_ids）。
"""

import os
import json
import time
import argparse
import statistics
from typing import List, Dict, Any

import chromadb


def load_jsonl(path: str) -> List[Dict[str, Any]]:
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                pass
    return items


def main():
    parser = argparse.ArgumentParser(description="ChromaDB 检索基准测试")
    parser.add_argument("--persist_dir", required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--queries", required=True)
    parser.add_argument("--n_results", default="5,10,20", help="逗号分隔的n_results列表")
    args = parser.parse_args()

    client = chromadb.PersistentClient(path=args.persist_dir)
    collection = client.get_collection(name=args.collection)

    queries = load_jsonl(args.queries)
    if not queries:
        raise RuntimeError("查询集为空")

    for n_str in args.n_results.split(","):
        n = int(n_str)
        latencies = []
        recalls = []

        for q in queries:
            text = q.get("text") or q.get("question")
            expected = set(q.get("expected_ids", []))
            if not text:
                continue
            start = time.perf_counter()
            res = collection.query(query_texts=[text], n_results=n)
            latency = time.perf_counter() - start
            latencies.append(latency)

            if expected:
                ids = set(res.get("ids", [[]])[0])
                hit = len(expected.intersection(ids))
                recalls.append(hit / len(expected) if expected else 0)

        avg = statistics.mean(latencies) if latencies else 0
        p95 = statistics.quantiles(latencies, n=100)[94] if len(latencies) >= 100 else (sorted(latencies)[int(0.95 * len(latencies))] if latencies else 0)
        p99 = statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else (sorted(latencies)[int(0.99 * len(latencies))] if latencies else 0)
        r_avg = statistics.mean(recalls) if recalls else 0
        print(f"n_results={n} avg={avg:.4f}s p95={p95:.4f}s p99={p99:.4f}s recall~={r_avg:.3f}")


if __name__ == "__main__":
    main()

