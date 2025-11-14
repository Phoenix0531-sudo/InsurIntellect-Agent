#!/usr/bin/env python3
"""
简单压力测试脚本：并发请求 /api/v1/queries/ask 端点，统计吞吐与延迟。

使用方法：
  python tools/stress_test_api.py --qps 20 --total 200 --question "测试：压力场景"

参数：
  --qps 并发数（线程数），默认 10
  --total 总请求数，默认 100
  --base_url 服务地址，默认 http://127.0.0.1:8000
"""

import time
import json
import argparse
import threading
from queue import Queue
import requests


def worker(base_url: str, payload: dict, results: list):
    url = f"{base_url.rstrip('/')}/api/v1/queries/ask"
    headers = {"Content-Type": "application/json"}
    start = time.perf_counter()
    try:
        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
        elapsed = time.perf_counter() - start
        results.append((r.status_code, elapsed))
    except Exception:
        elapsed = time.perf_counter() - start
        results.append((0, elapsed))


def main():
    parser = argparse.ArgumentParser(description="API 压力测试")
    parser.add_argument("--qps", type=int, default=10, help="并发线程数")
    parser.add_argument("--total", type=int, default=100, help="总请求数")
    parser.add_argument("--base_url", type=str, default="http://127.0.0.1:8000", help="服务地址")
    parser.add_argument("--question", type=str, default="压力测试：理赔流程有哪些材料？", help="测试问题")
    args = parser.parse_args()

    payload = {
        "question": args.question,
        "query_type": "general",
        "max_chunks": 3,
        "stream": False,
    }

    results = []
    threads = []

    start_total = time.perf_counter()
    for i in range(args.total):
        t = threading.Thread(target=worker, args=(args.base_url, payload, results))
        threads.append(t)
        t.start()
        # 简单节流：保持平均并发不超过 qps
        while sum(1 for th in threads if th.is_alive()) >= args.qps:
            time.sleep(0.005)

    for t in threads:
        t.join()
    total_elapsed = time.perf_counter() - start_total

    success = sum(1 for s, _ in results if s == 200)
    fail = len(results) - success
    latencies = [e for _, e in results]
    latencies.sort()

    p50 = latencies[int(0.50 * len(latencies))] if latencies else 0
    p95 = latencies[int(0.95 * len(latencies))] if latencies else 0
    p99 = latencies[int(0.99 * len(latencies))] if latencies else 0

    print("=== 压力测试结果 ===")
    print(f"总请求: {len(results)} 成功: {success} 失败: {fail}")
    print(f"总耗时: {total_elapsed:.3f}s, 吞吐: {len(results)/total_elapsed:.2f} req/s")
    print(f"延迟 P50: {p50:.3f}s P95: {p95:.3f}s P99: {p99:.3f}s")


if __name__ == "__main__":
    main()

