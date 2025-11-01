#!/usr/bin/env python3
"""
RAG 工作流离线测试
模拟检索与回答过程，评估检索质量
"""

from pathlib import Path
from typing import List, Dict, Tuple
from app.core.app_logging import setup_logging, get_logger

logger = get_logger(__name__)


def load_chunks(chunks_file: str) -> List[Dict]:
    """加载已分割的文本块 JSONL/JSON 文件。"""
    import json
    chunks = []
    path = Path(chunks_file)
    if not path.exists():
        logger.error(f"❌ 文件不存在: {chunks_file}")
        return chunks

    # 支持 .jsonl 和 .json
    try:
        if path.suffix.lower() == ".jsonl":
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    chunks.append(json.loads(line))
        else:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    chunks = data
                else:
                    logger.warning("⚠️  JSON 格式非列表，尝试从 'chunks' 键读取")
                    chunks = data.get("chunks", [])
        logger.info(f"✅ 加载文本块: {len(chunks)} 条")
    except Exception as e:
        logger.error(f"❌ 加载失败: {e}")
    return chunks


def simple_tfidf_retrieval(chunks: List[Dict], query: str, top_k: int = 5) -> List[Tuple[float, Dict]]:
    """纯 Python 相似度检索（无第三方依赖）。

    使用 difflib.SequenceMatcher 计算相似度，并结合长度归一化进行排序，
    在没有 scikit-learn 的环境下可用作离线快速评估。
    """
    from difflib import SequenceMatcher
    import math

    def score(text: str, q: str) -> float:
        if not text:
            return 0.0
        # 计算基础相似度
        base = SequenceMatcher(None, q, text).ratio()
        # 根据长度做轻微惩罚（过长文本降权）
        ln = len(text)
        penalty = 1.0 / (1.0 + math.log10(max(10, ln)))
        return float(base * penalty)

    ranked = []
    for c in chunks:
        s = score(c.get("text", ""), query)
        ranked.append((s, c))

    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked[:top_k]


def evaluate_retrieval(ranked: List[Tuple[float, Dict]], query: str) -> Dict:
    """评估检索结果的覆盖度与多样性。"""
    import math
    coverage = sum(1 for s, _ in ranked if s > 0.1) / max(len(ranked), 1)
    diversity = len({r[1].get("source_id", r[1].get("doc_id", "unknown")) for r in ranked}) / max(len(ranked), 1)
    avg_score = sum(s for s, _ in ranked) / max(len(ranked), 1)
    return {
        "query": query,
        "avg_score": round(avg_score, 4),
        "coverage": round(coverage, 4),
        "diversity": round(diversity, 4),
        "top_sources": [r[1].get("source", r[1].get("file", "unknown")) for r in ranked],
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="RAG 工作流离线测试")
    parser.add_argument("chunks_file", help="文本块 JSONL/JSON 文件路径")
    parser.add_argument("query", help="测试查询文本")
    parser.add_argument("--top_k", type=int, default=5, help="返回 TopK 结果")
    args = parser.parse_args()

    setup_logging(level="INFO")
    chunks = load_chunks(args.chunks_file)
    if not chunks:
        return

    ranked = simple_tfidf_retrieval(chunks, args.query, top_k=args.top_k)
    logger.info("\n📌 TopK 检索结果:")
    for i, (score, block) in enumerate(ranked, start=1):
        preview = block.get("text", "").replace("\n", " ")[:160]
        logger.info(f"{i:02d}. score={score:.4f} | {preview}")

    metrics = evaluate_retrieval(ranked, args.query)
    logger.info("\n📊 检索评估指标:")
    for k, v in metrics.items():
        logger.info(f"- {k}: {v}")


if __name__ == "__main__":
    main()
