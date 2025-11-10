#!/usr/bin/env python3
"""
Embedding 保险场景评测脚本（攻关任务一）

目标：横向评测不同嵌入模型（存根）在保险领域文档召回上的表现

特性：
- 模型接口可插拔（EmbeddingModelInterface 抽象基类）
- 提供 bge-large-zh-v1.5、gte-Qwen1.5-7B-instruct、text-embedding-ada-002 的存根实现
- 使用本地 ChromaDB（持久化路径 settings.CHROMA_PERSIST_DIRECTORY）
- 为每个模型使用独立集合（benchmark_*），避免向量空间混淆
- 计算 Recall@5/10/20 与 MRR，输出 Markdown 与 JSON 报告
- 文本确定性随机向量（基于模型名+文本内容+全局seed），确保可复现

用法：
    python scripts/embedding_benchmark.py \
        --cases tools/embedding_benchmark_cases.json \
        --report-dir reports \
        --seed 42
"""

import argparse
import json
import hashlib
import math
import os
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple

from app.core.config import settings
from app.core.app_logging import setup_logging, get_logger
from app.core.chromadb_manager import chroma_manager
try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None  # 运行时可选依赖，用于本地微调模型评测


# ----------------------------
# 抽象接口与存根模型
# ----------------------------

class EmbeddingModelInterface:
    """嵌入模型抽象基类（可插拔接口）。

    子类需要实现：
    - name: 模型名称（字符串）
    - dim:  向量维度（整数）
    - embed_documents(texts: List[str]) -> List[List[float]]
    - embed_query(text: str) -> List[float]
    """

    name: str
    dim: int

    def __init__(self, name: str, dim: int, global_seed: int = 42):
        self.name = name
        self.dim = dim
        self.global_seed = global_seed

    def _deterministic_vector(self, text: str) -> List[float]:
        """基于（模型名 + 文本 + 全局seed）生成确定性随机向量，并进行L2归一化。"""
        seed_str = f"{self.global_seed}|{self.name}|{text}"
        # 将字符串hash为整数seed
        h = hashlib.md5(seed_str.encode("utf-8")).hexdigest()
        seed_int = int(h, 16) % (2**31)
        rng = random.Random(seed_int)
        vec = [(rng.random() * 2.0 - 1.0) for _ in range(self.dim)]
        # L2 归一化，避免长度差异影响余弦相似度
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._deterministic_vector(t or "") for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._deterministic_vector(text or "")


class BgeLargeZhV15Stub(EmbeddingModelInterface):
    def __init__(self, global_seed: int = 42):
        super().__init__(name="bge-large-zh-v1.5", dim=1024, global_seed=global_seed)


class GteQwen15_7BInstructStub(EmbeddingModelInterface):
    def __init__(self, global_seed: int = 42):
        super().__init__(name="gte-Qwen1.5-7B-instruct", dim=1024, global_seed=global_seed)


class Ada002Stub(EmbeddingModelInterface):
    def __init__(self, global_seed: int = 42):
        super().__init__(name="text-embedding-ada-002", dim=1536, global_seed=global_seed)


class SentenceTransformersModel(EmbeddingModelInterface):
    """基于 sentence-transformers 的真实嵌入模型包装，用于评测本地或HF模型。"""

    def __init__(self, model_id_or_path: str, global_seed: int = 42):
        if SentenceTransformer is None:
            raise RuntimeError("sentence-transformers 未安装，无法加载真实模型")
        self._st_model = SentenceTransformer(model_id_or_path)
        dim = int(self._st_model.get_sentence_embedding_dimension())
        super().__init__(name=model_id_or_path, dim=dim, global_seed=global_seed)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._st_model.encode(texts or [""], normalize_embeddings=True, batch_size=64)

    def embed_query(self, text: str) -> List[float]:
        return self._st_model.encode([text or ""], normalize_embeddings=True)[0]


# ----------------------------
# 数据结构与评测指标
# ----------------------------

@dataclass
class CorpusDoc:
    id: str
    title: str
    content: str
    product_type: str
    version: str
    is_expired: bool


@dataclass
class QueryCase:
    id: str
    text: str
    relevant_doc_ids: List[str]


def recall_at_k(results_ids: List[str], relevant_ids: List[str], k: int) -> float:
    """计算单查询的 Recall@K。"""
    if not relevant_ids:
        return 0.0
    topk = set(results_ids[:k])
    hits = sum(1 for r in relevant_ids if r in topk)
    return hits / float(len(relevant_ids))


def reciprocal_rank(results_ids: List[str], relevant_ids: List[str]) -> float:
    """计算单查询的 Reciprocal Rank（MRR的基础）。"""
    ranks = [i + 1 for i, rid in enumerate(results_ids) if rid in set(relevant_ids)]
    if not ranks:
        return 0.0
    return 1.0 / float(min(ranks))


# ----------------------------
# ChromaDB 集合辅助
# ----------------------------

def ensure_fresh_collection(client, name: str):
    """删除并创建一个干净的集合（hnsw:space=cosine）。"""
    try:
        client.delete_collection(name=name)
    except Exception:
        pass
    return client.create_collection(name=name, metadata={"hnsw:space": "cosine"})


def add_corpus_to_collection(collection, model: EmbeddingModelInterface, corpus: List[CorpusDoc]) -> None:
    ids = [d.id for d in corpus]
    documents = [d.content for d in corpus]
    metadatas = [
        {
            "doc_id": d.id,
            "title": d.title,
            "product_type": d.product_type,
            "version": d.version,
            "is_expired": d.is_expired,
        }
        for d in corpus
    ]
    embeddings = model.embed_documents(documents)
    collection.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)


def query_collection(collection, model: EmbeddingModelInterface, query_text: str, top_k: int = 20) -> List[str]:
    qvec = model.embed_query(query_text)
    # 注意：chromadb 0.5.x 的 include 不支持 "ids"，默认返回 ids，无需显式 include
    res = collection.query(query_embeddings=[qvec], n_results=top_k)  # type: ignore
    ids = res.get("ids") or []
    if isinstance(ids, list) and ids:
        return ids[0]
    return []


# ----------------------------
# 报告生成
# ----------------------------

def generate_markdown_report(
    report_path: Path,
    seed: int,
    corpus_stats: Dict[str, Any],
    model_results: List[Dict[str, Any]],
) -> None:
    lines: List[str] = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines.append(f"# Embedding保险场景评测报告")
    lines.append("")
    lines.append(f"- 生成时间: {ts}")
    lines.append(f"- 全局随机种子: `{seed}`")
    lines.append(f"- Chroma 路径: `{settings.CHROMA_PERSIST_DIRECTORY}`")
    lines.append("")
    lines.append("**数据集概览**")
    lines.append(f"- 文档数: {corpus_stats['num_docs']}")
    lines.append(f"- 查询数: {corpus_stats['num_queries']}")
    lines.append(f"- 每查询相关文档数: {corpus_stats['relevant_per_query']}")
    lines.append("")
    lines.append("**模型结果**")
    for mr in model_results:
        lines.append(f"- 模型 `{mr['model_name']}` （维度 {mr['dim']}，集合 `{mr['collection_name']}`）")
        lines.append(
            f"  - Recall@5: {mr['metrics']['recall@5']:.4f} | Recall@10: {mr['metrics']['recall@10']:.4f} | Recall@20: {mr['metrics']['recall@20']:.4f} | MRR: {mr['metrics']['mrr']:.4f}"
        )
    lines.append("")
    lines.append("**结论与建议**")
    lines.append("- 本报告基于存根模型的确定性向量，数值仅用于流程与指标验证。")
    lines.append("- 替换为真实嵌入模型后，保持集合独立以避免维度/空间混淆。")
    lines.append("- 扩充查询与标注可提高评测稳定性；建议每查询≥2个相关文档。")

    report_path.write_text("\n".join(lines), encoding="utf-8")


# ----------------------------
# 主流程
# ----------------------------

def main():
    parser = argparse.ArgumentParser(description="Embedding 保险场景评测（存根模型，ChromaDB 持久化）")
    parser.add_argument("--cases", type=str, default="tools/embedding_benchmark_cases.json", help="数据与标注文件路径")
    parser.add_argument("--report-dir", type=str, default="reports", help="报告输出目录")
    parser.add_argument("--seed", type=int, default=42, help="全局随机种子")
    args = parser.parse_args()

    os.makedirs(args.report_dir, exist_ok=True)
    logger = setup_logging(log_level=settings.LOG_LEVEL, log_file=os.path.join(args.report_dir, "embedding_benchmark.log"))
    logger.info("开始执行 Embedding 保险场景评测（存根模型）")

    # 加载数据与标注
    cases_path = Path(args.cases)
    if not cases_path.exists():
        logger.error(f"标注文件不存在: {cases_path}")
        raise FileNotFoundError(str(cases_path))
    raw = json.loads(cases_path.read_text(encoding="utf-8"))

    # 解析语料
    corpus: List[CorpusDoc] = []
    for d in raw.get("corpus", []):
        corpus.append(
            CorpusDoc(
                id=d["id"],
                title=d.get("title", d["id"]),
                content=d.get("content", ""),
                product_type=d.get("product_type", "未知"),
                version=d.get("version", "v1"),
                is_expired=bool(d.get("is_expired", False)),
            )
        )

    # 解析查询
    queries: List[QueryCase] = []
    for q in raw.get("queries", []):
        rel = q.get("relevant_doc_ids", [])
        queries.append(QueryCase(id=q.get("id", q.get("query_id", "q")), text=q.get("text", q.get("query", "")), relevant_doc_ids=rel))

    if not corpus or not queries:
        logger.error("语料或查询为空，无法评测")
        raise ValueError("corpus_or_queries_empty")

    # 构造模型列表（存根实现）
    global_seed = args.seed
    models: List[EmbeddingModelInterface] = [
        BgeLargeZhV15Stub(global_seed=global_seed),
        GteQwen15_7BInstructStub(global_seed=global_seed),
        Ada002Stub(global_seed=global_seed),
    ]

    # 加入真实模型：基础模型与本地微调模型（若存在）
    if SentenceTransformer is not None:
        try:
            models.append(SentenceTransformersModel("BAAI/bge-large-zh-v1.5", global_seed=global_seed))
        except Exception:
            pass
        local_model_dir = Path("models/finetuned_embedding_v1")
        if local_model_dir.exists():
            try:
                models.append(SentenceTransformersModel(str(local_model_dir), global_seed=global_seed))
            except Exception:
                pass

    # 获取 Chroma 持久客户端
    client = chroma_manager.get_client()

    # 评测结果聚合
    model_results: List[Dict[str, Any]] = []

    for m in models:
        safe_name = (
            m.name.replace('/', '_').replace('\\', '_').replace('-', '_').replace('.', '_')
        )
        collection_name = f"benchmark_{safe_name}"
        logger.info(f"准备模型集合: {collection_name} (dim={m.dim})")
        collection = ensure_fresh_collection(client, collection_name)
        add_corpus_to_collection(collection, m, corpus)
        logger.info(f"已写入语料到集合 {collection_name}，向量数: {collection.count()}")

        # 逐查询评测
        recalls_5: List[float] = []
        recalls_10: List[float] = []
        recalls_20: List[float] = []
        rr_list: List[float] = []

        for qc in queries:
            ids = query_collection(collection, m, qc.text, top_k=20)
            recalls_5.append(recall_at_k(ids, qc.relevant_doc_ids, 5))
            recalls_10.append(recall_at_k(ids, qc.relevant_doc_ids, 10))
            recalls_20.append(recall_at_k(ids, qc.relevant_doc_ids, 20))
            rr_list.append(reciprocal_rank(ids, qc.relevant_doc_ids))

        metrics = {
            "recall@5": round(sum(recalls_5) / len(recalls_5), 4),
            "recall@10": round(sum(recalls_10) / len(recalls_10), 4),
            "recall@20": round(sum(recalls_20) / len(recalls_20), 4),
            "mrr": round(sum(rr_list) / len(rr_list), 4),
        }

        model_results.append(
            {
                "model_name": m.name,
                "dim": m.dim,
                "collection_name": collection_name,
                "metrics": metrics,
            }
        )

    # 输出报告
    ts2 = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_path = Path(args.report_dir) / f"embedding_benchmark_insurance_{ts2}.md"
    json_path = Path(args.report_dir) / f"embedding_benchmark_insurance_{ts2}.json"

    corpus_stats = {
        "num_docs": len(corpus),
        "num_queries": len(queries),
        "relevant_per_query": 2,
    }
    generate_markdown_report(md_path, global_seed, corpus_stats, model_results)

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "seed": global_seed,
                "chroma_path": settings.CHROMA_PERSIST_DIRECTORY,
                "corpus_stats": corpus_stats,
                "results": model_results,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    logger.info(f"报告已生成: {md_path}")
    logger.info(f"JSON结果已生成: {json_path}")


if __name__ == "__main__":
    main()
